import os
import re
import json
import hashlib
import unicodedata
import numpy as np
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from pypdf import PdfReader
import math
from collections import Counter
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------- Configuración
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUTA_PDF = os.path.join(BASE_DIR, "Data", "constitucio-politica-colombia-1991.pdf")
CACHE_DIR = os.path.join(BASE_DIR, "cache")

MODELO_EMBEDDINGS = "paraphrase-multilingual-MiniLM-L12-v2"
# Opción más fuerte (pesa ~2 GB). Con el caché solo se calcula una vez:
# MODELO_EMBEDDINGS = "BAAI/bge-m3"
MAX_SEQ = 256  # con bge-m3 puedes subir a 512

MAX_PALABRAS = 120
SOLAPE = 20

app = Flask(__name__)
CORS(app)

embedder = SentenceTransformer(MODELO_EMBEDDINGS)
embedder.max_seq_length = MAX_SEQ


# ---------------------------------------------------------------- LLM
def llamar_llm(messages, model="deepseek/deepseek-chat"):
    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
            "HTTP-Referer": "http://localhost",
            "X-Title": "RAG Constitucion",
        },
        json={"model": model, "messages": messages, "temperature": 0.1},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


# ---------------------------------------------------------------- Indexación
def cargar_y_fragmentar_pdf(ruta_pdf, max_palabras=MAX_PALABRAS, solape=SOLAPE):
    if not os.path.exists(ruta_pdf):
        raise FileNotFoundError(f"No se encontró el archivo: {ruta_pdf}")

    reader = PdfReader(ruta_pdf)

    # Texto completo y posición donde empieza cada página
    texto, inicios = "", []
    for num, pagina in enumerate(reader.pages, start=1):
        inicios.append((len(texto), num))
        texto += (pagina.extract_text() or "") + "\n"

    if not texto.strip():
        raise ValueError("No se extrajo texto del PDF (¿está escaneado?).")

    def pagina_de(pos):
        pag = 1
        for ini, num in inicios:
            if ini <= pos:
                pag = num
            else:
                break
        return pag

    patron = re.compile(
        r"^\s*ART[IÍ]CULO\s+(\d+)\s*[oOºª°]?\s*\.",
        re.IGNORECASE | re.MULTILINE,
    )
    coincidencias = list(patron.finditer(texto))

    segmentos = []  # (numero_articulo, pagina, texto)
    if len(coincidencias) >= 50:
        for i, m in enumerate(coincidencias):
            fin = coincidencias[i + 1].start() if i + 1 < len(coincidencias) else len(texto)
            segmentos.append((int(m.group(1)), pagina_de(m.start()), texto[m.start():fin]))
    else:
        print("AVISO: no se detectaron artículos; se fragmenta solo por palabras.")
        segmentos.append((None, 1, texto))

    chunks, articulos = [], []
    paso = max(1, max_palabras - solape)
    for num, pag, seg in segmentos:
        palabras = seg.split()
        etiqueta = f"[Art. {num} | Pág. {pag}]" if num else f"[Pág. {pag}]"
        if len(palabras) <= max_palabras:
            trozos = [" ".join(palabras)]
        else:
            trozos = [" ".join(palabras[i:i + max_palabras]) for i in range(0, len(palabras), paso)]
        for t in trozos:
            if t:
                chunks.append(f"{etiqueta} {t}")
                articulos.append(num)

    return chunks, articulos


# ---------------------------------------------------------------- Caché en disco
def firma_cache():
    """Cambia si cambia el PDF, el modelo o los parámetros de fragmentación."""
    st = os.stat(RUTA_PDF)
    base = f"{MODELO_EMBEDDINGS}|{MAX_SEQ}|{MAX_PALABRAS}|{SOLAPE}|{st.st_size}|{int(st.st_mtime)}|v1"
    return hashlib.md5(base.encode()).hexdigest()


def cargar_o_crear_indice():
    os.makedirs(CACHE_DIR, exist_ok=True)
    ruta_chunks = os.path.join(CACHE_DIR, "chunks.json")
    ruta_emb = os.path.join(CACHE_DIR, "embeddings.npy")
    ruta_meta = os.path.join(CACHE_DIR, "meta.json")
    firma = firma_cache()

    if all(os.path.exists(p) for p in (ruta_chunks, ruta_emb, ruta_meta)):
        try:
            with open(ruta_meta, encoding="utf-8") as f:
                meta = json.load(f)
            if meta.get("firma") == firma:
                print("Cargando índice desde caché...")
                with open(ruta_chunks, encoding="utf-8") as f:
                    datos = json.load(f)
                emb = np.load(ruta_emb)
                if len(emb) == len(datos["chunks"]):
                    return datos["chunks"], datos["articulos"], emb
        except Exception as e:
            print(f"Caché inválido ({e}); se reconstruye.")

    print("Indexando PDF (primera vez o cambió el PDF/modelo)...")
    chunks, articulos = cargar_y_fragmentar_pdf(RUTA_PDF)
    emb = embedder.encode(chunks, normalize_embeddings=True, show_progress_bar=True)

    with open(ruta_chunks, "w", encoding="utf-8") as f:
        json.dump({"chunks": chunks, "articulos": articulos}, f, ensure_ascii=False)
    np.save(ruta_emb, emb)
    with open(ruta_meta, "w", encoding="utf-8") as f:
        json.dump({"firma": firma}, f)
    print("Índice guardado en caché.")
    return chunks, articulos, emb

class BM25Okapi:
    """BM25 mínimo, compatible con el uso que le damos (get_scores)."""

    def __init__(self, corpus, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.docs = [Counter(doc) for doc in corpus]
        self.largos = [len(doc) for doc in corpus]
        self.avgdl = sum(self.largos) / max(1, len(self.largos))
        n = len(corpus)
        df = Counter()
        for doc in self.docs:
            df.update(doc.keys())
        self.idf = {t: math.log((n - f + 0.5) / (f + 0.5) + 1) for t, f in df.items()}

    def get_scores(self, consulta):
        puntajes = np.zeros(len(self.docs))
        for t in set(consulta):
            idf = self.idf.get(t)
            if idf is None:
                continue
            for i, doc in enumerate(self.docs):
                f = doc.get(t, 0)
                if f:
                    norm = 1 - self.b + self.b * self.largos[i] / self.avgdl
                    puntajes[i] += idf * f * (self.k1 + 1) / (f + self.k1 * norm)
        return puntajes
# ---------------------------------------------------------------- Búsqueda
STOP = {"que", "los", "las", "del", "una", "por", "con", "para", "como", "cual",
        "cuales", "segun", "sobre", "dice", "este", "esta", "son", "ser", "sus",
        "han", "hay", "puede", "pueden", "constitucion", "colombia"}


def tokenizar(texto):
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    # t[:6] es un "stemmer" tosco: garantiza/garantizar/garantías -> "garant"
    return [t[:6] for t in re.findall(r"\w+", texto) if len(t) > 2 and t not in STOP]


def expandir_consulta(pregunta, historial):
    contexto_hist = "\n".join(f"{m['rol']}: {m['texto'][:300]}" for m in historial[-4:])
    prompt = f"""Eres experto en la Constitución Política de Colombia de 1991.
Escribe 3 consultas de búsqueda distintas para encontrar en el texto constitucional la respuesta a la pregunta.
Usa el vocabulario del texto (derecho, garantiza, prohíbe, artículo, autoridad, etc.) y menciona números de artículo solo si los conoces.
Si la pregunta es un seguimiento de la conversación, hazla autónoma.
Responde solo con las 3 consultas, una por línea, sin numeración ni explicaciones.

Conversación previa:
{contexto_hist or '(ninguna)'}

Pregunta: {pregunta}"""
    try:
        salida = llamar_llm([{"role": "user", "content": prompt}])
        extra = [l.strip("-•*0123456789. ").strip() for l in salida.split("\n") if l.strip()][:3]
    except Exception:
        extra = []
    return [pregunta] + extra


def recuperar(consultas, top_k=10, k_rrf=60):
    puntajes = {}
    for q in consultas:
        q_emb = embedder.encode(q, normalize_embeddings=True)
        semantico = np.argsort(chunk_embeddings @ q_emb)[::-1][:30]
        lexico = np.argsort(bm25.get_scores(tokenizar(q)))[::-1][:30]
        for ranking in (semantico, lexico):
            for pos, i in enumerate(ranking):
                puntajes[int(i)] = puntajes.get(int(i), 0) + 1 / (k_rrf + pos + 1)
    return [i for i, _ in sorted(puntajes.items(), key=lambda x: -x[1])[:top_k]]


# ---------------------------------------------------------------- RAG
def rag(pregunta, historial=None, top_k=10):
    historial = historial or []
    consultas = expandir_consulta(pregunta, historial)
    indices = recuperar(consultas, top_k)

    # Artículos mencionados explícitamente ("artículo 29")
    for num in re.findall(r"art[ií]culo\s+(\d+)", pregunta, re.IGNORECASE):
        for i, a in enumerate(articulos):
            if a == int(num) and i not in indices:
                indices.append(i)

    # Si un artículo largo quedó cortado, incluir su continuación
    for i in list(indices):
        if i + 1 < len(chunks) and articulos[i] is not None and articulos[i + 1] == articulos[i]:
            if i + 1 not in indices:
                indices.append(i + 1)

    indices = sorted(set(indices))
    print("Consultas:", consultas)
    print("Recuperados:", [chunks[i][:22] for i in indices])
    contexto = "\n\n".join(chunks[i] for i in indices)

    prompt = f"""Responde la pregunta con base en el siguiente contexto de la Constitución Política de Colombia.
- Cita siempre el número de artículo y la página.
- Si el contexto cubre la pregunta solo en parte, responde lo que sí respalda y aclara qué falta.
- Di que no está en el contexto solo si realmente no hay nada relacionado.
- No inventes contenido que no aparezca en el contexto.

Contexto:
{contexto}

Pregunta: {pregunta}
"""
    mensajes = [{
        "role": "system",
        "content": "Eres un asistente experto en la Constitución colombiana. Respondes en español, de forma clara y fundamentada en el contexto provisto.",
    }]
    for m in historial[-6:]:
        mensajes.append({
            "role": "user" if m["rol"] == "user" else "assistant",
            "content": m["texto"],
        })
    mensajes.append({"role": "user", "content": prompt})
    return llamar_llm(mensajes)


# ---------------------------------------------------------------- Arranque
chunks, articulos, chunk_embeddings = cargar_o_crear_indice()
bm25 = BM25Okapi([tokenizar(c) for c in chunks])
print(f"Listo: {len(chunks)} fragmentos, {len(set(a for a in articulos if a))} artículos.")


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    pregunta = (data.get("pregunta") or "").strip()
    if not pregunta:
        return jsonify({"error": "Falta la pregunta"}), 400
    try:
        return jsonify({"respuesta": rag(pregunta, data.get("historial", []))})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(port=5000, debug=True, use_reloader=False)