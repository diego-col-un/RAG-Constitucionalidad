import os
import re
import json
import hashlib
import unicodedata
import math
from collections import Counter
import numpy as np
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------- Configuración
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUTA_PDF = os.path.join(BASE_DIR, "Data", "constitucio-politica-colombia-1991.pdf")
CACHE_DIR = os.path.join(BASE_DIR, "cache")

MODELO_EMBEDDINGS = "paraphrase-multilingual-MiniLM-L12-v2"
MAX_SEQ = 256
MAX_PALABRAS = 120
SOLAPE = 20

app = Flask(__name__)
CORS(app)

embedder = SentenceTransformer(MODELO_EMBEDDINGS)
embedder.max_seq_length = MAX_SEQ


# ---------------------------------------------------------------- LLM
def llamar_llm(messages, model="deepseek/deepseek-chat", temperature=0.1):
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Falta configurar OPENROUTER_API_KEY en el archivo .env")

    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {os.environ.get("OPENROUTER_API_KEY", "")}",
            "HTTP-Referer": "http://localhost",
            "X-Title": "RAG Constitucion Colombia 1991",
        },
        json={"model": model, "messages": messages, "temperature": temperature},
        timeout=75,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


# ---------------------------------------------------------------- Indexación
def cargar_y_fragmentar_pdf(ruta_pdf, max_palabras=MAX_PALABRAS, solape=SOLAPE):
    if not os.path.exists(ruta_pdf):
        raise FileNotFoundError(f"No se encontró el archivo: {ruta_pdf}")

    reader = PdfReader(ruta_pdf)

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

    segmentos = []
    if len(coincidencias) >= 50:
        for i, m in enumerate(coincidencias):
            fin = coincidencias[i + 1].start() if i + 1 < len(coincidencias) else len(texto)
            segmentos.append((int(m.group(1)), pagina_de(m.start()), texto[m.start():fin]))
    else:
        segmentos.append((None, 1, texto))

    chunks, articulos, paginas = [], [], []
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
                paginas.append(pag)

    return chunks, articulos, paginas


# ---------------------------------------------------------------- Caché en disco
def firma_cache():
    st = os.stat(RUTA_PDF)
    base = f"{MODELO_EMBEDDINGS}|{MAX_SEQ}|{MAX_PALABRAS}|{SOLAPE}|{st.st_size}|{int(st.st_mtime)}|v2"
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
                if len(emb) == len(datos["chunks"]) and "paginas" in datos:
                    return datos["chunks"], datos["articulos"], datos["paginas"], emb
        except Exception as e:
            print(f"Caché inválido ({e}); se reconstruye.")

    print("Indexando PDF...")
    chunks, articulos, paginas = cargar_y_fragmentar_pdf(RUTA_PDF)
    emb = embedder.encode(chunks, normalize_embeddings=True, show_progress_bar=True)

    with open(ruta_chunks, "w", encoding="utf-8") as f:
        json.dump(
            {"chunks": chunks, "articulos": articulos, "paginas": paginas},
            f,
            ensure_ascii=False,
        )
    np.save(ruta_emb, emb)
    with open(ruta_meta, "w", encoding="utf-8") as f:
        json.dump({"firma": firma}, f)
    print("Índice guardado en caché.")
    return chunks, articulos, paginas, emb


class BM25Okapi:
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
STOP = {
    "que", "los", "las", "del", "una", "por", "con", "para", "como", "cual",
    "cuales", "segun", "sobre", "dice", "este", "esta", "son", "ser", "sus",
    "han", "hay", "puede", "pueden", "constitucion", "colombia"
}


def tokenizar(texto):
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return [t[:6] for t in re.findall(r"\w+", texto) if len(t) > 2 and t not in STOP]


def expandir_consulta(pregunta, historial, modo="consulta"):
    contexto_hist = "\n".join(f"{m['rol']}: {m['texto'][:300]}" for m in historial[-4:])
    enfoque = (
        "Identifica qué derechos fundamentales podrían estar vulnerados y qué mecanismo constitucional aplica (tutela art. 86, petición art. 23, hábeas corpus art. 30, acción popular art. 88, cumplimiento art. 87)."
        if modo == "caso"
        else "Usa el vocabulario del texto constitucional."
    )
    prompt = f"""Eres experto en la Constitución Política de Colombia de 1991.
Escribe 3 consultas de búsqueda distintas para encontrar en el texto constitucional los artículos relevantes.
{enfoque}
Responde solo con las 3 consultas, una por línea, sin numeración ni explicaciones.

Conversación previa:
{contexto_hist or '(ninguna)'}

Entrada: {pregunta}"""
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


# ---------------------------------------------------------------- Ingeniería Jurídica Determinística
def auditar_citas(respuesta_texto):
    """
    Verifica matemáticamente cada artículo citado en la respuesta contra los embeddings
    reales del PDF para detectar alucinaciones o interpretaciones extensivas.
    """
    oraciones = re.split(r"(?<=[.!?\n])\s+", respuesta_texto)
    patron_cita = re.compile(r"(?:\[Art\.\s*|Art[ií]culo\s+)(\d+)", re.IGNORECASE)
    citas_eval = {}

    for oracion in oraciones:
        nums = patron_cita.findall(oracion)
        if not nums:
            continue
        oracion_limpia = re.sub(r"\[.*?\]|\*\*", "", oracion).strip()
        if len(oracion_limpia) < 15:
            continue

        emb_oracion = embedder.encode(oracion_limpia, normalize_embeddings=True)

        for n_str in nums:
            num = int(n_str)
            indices_art = [idx for idx, a in enumerate(articulos) if a == num]

            if not indices_art:
                citas_eval[num] = {
                    "articulo": num,
                    "score": 0,
                    "estado": "alerta",
                    "etiqueta": "No existe en el PDF",
                }
                continue

            # Similitud coseno máxima entre la afirmación de la IA y los fragmentos reales del artículo
            sim_max = float(np.max(chunk_embeddings[indices_art] @ emb_oracion))
            # Escalar similitud semántica (0.35 - 0.85) a porcentaje interpretable (0 - 100%)
            porcentaje = int(np.clip(((sim_max - 0.30) / 0.52) * 100, 12, 99))

            if porcentaje >= 68:
                estado, etiqueta = "verificado", "Cita Exacta"
            elif porcentaje >= 45:
                estado, etiqueta = "extensivo", "Interpretación Doctrinal"
            else:
                estado, etiqueta = "alerta", "Baja Correspondencia"

            # Guardar la mejor evaluación encontrada para ese artículo en la respuesta
            if num not in citas_eval or porcentaje > citas_eval[num]["score"]:
                citas_eval[num] = {
                    "articulo": num,
                    "score": porcentaje,
                    "estado": estado,
                    "etiqueta": etiqueta,
                }

    lista = sorted(citas_eval.values(), key=lambda x: x["articulo"])
    rigor_global = (
        int(sum(c["score"] for c in lista) / len(lista)) if lista else 100
    )
    return lista, rigor_global


def construir_grafo_conexidad(indices_recuperados, top_n=5):
    """
    Calcula por álgebra lineal (producto punto de embeddings) la red de conexidad
    sistemática entre el artículo eje de la consulta y los demás artículos de la Carta.
    """
    arts_candidatos = [articulos[i] for i in indices_recuperados if articulos[i] is not None]
    if not arts_candidatos:
        return None

    # Artículo más frecuente entre los fragmentos recuperados como nodo central
    art_central = Counter(arts_candidatos).most_common(1)[0][0]
    indices_central = [i for i, a in enumerate(articulos) if a == art_central]
    if not indices_central:
        return None

    # Vector promedio normalizado del artículo central
    vec_central = np.mean(chunk_embeddings[indices_central], axis=0)
    vec_central = vec_central / (np.linalg.norm(vec_central) + 1e-12)

    similitudes = chunk_embeddings @ vec_central
    mejores_por_art = {}

    for idx, sim in enumerate(similitudes):
        art = articulos[idx]
        if art is None or art == art_central:
            continue
        if art not in mejores_por_art or sim > mejores_por_art[art]["sim"]:
            extracto = re.sub(r"^\[.*?\]\s*", "", chunks[idx])[:180] + "..."
            mejores_por_art[art] = {
                "articulo": art,
                "pagina": paginas[idx],
                "sim": float(sim),
                "afinidad": int(np.clip(sim * 100, 40, 98)),
                "resumen": extracto,
            }

    relacionados = sorted(mejores_por_art.values(), key=lambda x: -x["sim"])[:top_n]
    extracto_central = re.sub(r"^\[.*?\]\s*", "", chunks[indices_central[0]])[:200] + "..."

    return {
        "central": {
            "articulo": art_central,
            "pagina": paginas[indices_central[0]],
            "resumen": extracto_central,
        },
        "relacionados": relacionados,
    }


# ---------------------------------------------------------------- RAG
def rag(pregunta, historial=None, modo="consulta", top_k=10):
    historial = historial or []
    consultas = expandir_consulta(pregunta, historial, modo)
    indices = recuperar(consultas, top_k)

    articulos_forzados = [int(n) for n in re.findall(r"art[ií]culo\s+(\d+)", pregunta, re.IGNORECASE)]
    if modo == "caso":
        articulos_forzados.extend([23, 86])

    for num in set(articulos_forzados):
        for i, a in enumerate(articulos):
            if a == num and i not in indices:
                indices.append(i)

    for i in list(indices):
        if i + 1 < len(chunks) and articulos[i] is not None and articulos[i + 1] == articulos[i]:
            if i + 1 not in indices:
                indices.append(i + 1)

    indices = sorted(set(indices))
    contexto = "\n\n".join(chunks[i] for i in indices)

    fuentes = []
    vistos = set()
    for i in indices:
        art = articulos[i]
        pag = paginas[i]
        clave = (art, pag)
        texto_limpio = re.sub(r"^\[.*?\]\s*", "", chunks[i])
        if clave not in vistos:
            vistos.add(clave)
            fuentes.append({
                "articulo": art,
                "pagina": pag,
                "extracto": texto_limpio,
            })
        else:
            for f in fuentes:
                if f["articulo"] == art and f["pagina"] == pag:
                    f["extracto"] += " " + texto_limpio

    identidad = (
        "Eres un asistente jurídico experto en la Constitución Política de Colombia de 1991, "
        "creado y desarrollado por Santiago Cardona Libreros (Santy) y su compañero de equipo para el convenio SUMA. "
        "Si te preguntan quién te creó, responde con orgullo mencionando a tus creadores."
    )

    if modo == "caso":
        system_prompt = (
            f"{identidad} Actúas como un consultorio jurídico constitucional. "
            "Analizas casos ciudadanos con rigor dogmático y redactas borradores legales listos para usar."
        )
        user_prompt = f"""Analiza el siguiente caso práctico ciudadano utilizando ÚNICAMENTE los artículos provistos en el contexto de la Constitución Política de Colombia de 1991.

Estructura tu respuesta EXACTAMENTE con estas 4 secciones claras:

1. **Diagnóstico de Derechos Vulnerados:** Identifica qué derechos fundamentales o constitucionales están en riesgo o vulnerados, citando siempre [Art. X | Pág. Y] y explicando por qué.
2. **Mecanismo Constitucional Idóneo y Procedibilidad:** Determina cuál acción constitucional procede (ej. Acción de Tutela - Art. 86, Derecho de Petición - Art. 23, Hábeas Corpus - Art. 30, etc.) y analiza brevemente requisitos de procedibilidad (subsidiariedad, inmediatez o perjuicio irremediable).
3. **Fundamentación Textual:** Cita textualmente los apartes clave de los artículos recuperados que respaldan el caso.
4. **Borrador del Escrito Constitucional:** Redacta un modelo formal completo (con encabezado al Juez o Entidad, identificación del accionante con espacios [COMPLETAR], Hechos numerados basados en el caso, Fundamentos de Derecho citando los artículos de la Constitución de 1991, Pretensiones concretas y Juramento/Notificaciones) listo para descargar y presentar.

Contexto constitucional recuperado:
{contexto}

Caso del ciudadano: {pregunta}
"""
    else:
        system_prompt = (
            f"{identidad} Respondes en español de forma clara, estructurada y fundamentada exclusivamente en el contexto provisto."
        )
        user_prompt = f"""Responde la pregunta con base en el siguiente contexto de la Constitución Política de Colombia (a menos que sea una pregunta sobre tu identidad o creadores).
- Cita siempre el número de artículo y la página en formato [Art. X | Pág. Y].
- Si el contexto cubre la pregunta solo en parte, responde lo que sí respalda y aclara qué falta.
- Di que no está en el contexto solo si realmente no hay nada relacionado.
- No inventes contenido constitucional que no aparezca en el contexto.

Contexto:
{contexto}

Pregunta: {pregunta}
"""

    mensajes = [{"role": "system", "content": system_prompt}]
    for m in historial[-6:]:
        mensajes.append({
            "role": "user" if m["rol"] == "user" else "assistant",
            "content": m["texto"],
        })
    mensajes.append({"role": "user", "content": user_prompt})

    respuesta = llamar_llm(mensajes)
    auditoria_citas, rigor_global = auditar_citas(respuesta)
    grafo = construir_grafo_conexidad(indices)

    return {
        "respuesta": respuesta,
        "fuentes": fuentes,
        "auditoria": auditoria_citas,
        "rigor_global": rigor_global,
        "grafo": grafo,
        "modo": modo,
    }


# ---------------------------------------------------------------- Arranque
chunks, articulos, paginas, chunk_embeddings = cargar_o_crear_indice()
bm25 = BM25Okapi([tokenizar(c) for c in chunks])
print(f"Listo: {len(chunks)} fragmentos, {len(set(a for a in articulos if a))} artículos.")


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    pregunta = (data.get("pregunta") or "").strip()
    modo = data.get("modo", "consulta")
    if not pregunta:
        return jsonify({"error": "Falta la pregunta"}), 400
    try:
        resultado = rag(pregunta, data.get("historial", []), modo=modo)
        return jsonify(resultado)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(port=5000, debug=True, use_reloader=False)