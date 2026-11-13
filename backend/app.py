import os
import numpy as np
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
import re

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUTA_PDF = os.path.join(BASE_DIR, "Data", "constitucio-politica-colombia-1991.pdf")

app = Flask(__name__)
CORS(app)

embedder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
embedder.max_seq_length = 256

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


def cargar_y_fragmentar_pdf(ruta_pdf, max_palabras=120, solape=20):
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
    paso = max_palabras - solape
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

def rag(pregunta, top_k=8):
    query_emb = embedder.encode(pregunta, normalize_embeddings=True)
    similitudes = chunk_embeddings @ query_emb
    indices = [int(i) for i in np.argsort(similitudes)[::-1][:top_k]]

    # Si la pregunta menciona un artículo ("artículo 29"), se incluye siempre
    for num in re.findall(r"art[ií]culo\s+(\d+)", pregunta, re.IGNORECASE):
        for i, a in enumerate(articulos):
            if a == int(num) and i not in indices:
                indices.insert(0, i)

    print("Recuperados:", [chunks[i][:22] for i in indices])  # para depurar
    contexto = "\n\n".join(chunks[i] for i in indices)

    prompt = f"""Responde a la pregunta únicamente con base en el siguiente contexto recuperado de la Constitución.
Si la respuesta no está en el contexto, dilo claramente. Cita el número de artículo y la página cuando sea posible.

Contexto:
{contexto}

Pregunta: {pregunta}
"""
    return llamar_llm([
        {
            "role": "system",
            "content": "Eres un asistente útil que responde únicamente fundamentado en el contexto provisto.",
        },
        {"role": "user", "content": prompt},
    ])

# Indexación una sola vez al arrancar el servidor
print("Indexando PDF...")
chunks, articulos = cargar_y_fragmentar_pdf(RUTA_PDF)
chunk_embeddings = embedder.encode(chunks, normalize_embeddings=True, show_progress_bar=True)
print(f"Listo: {len(chunks)} fragmentos, {len(set(a for a in articulos if a))} artículos.")


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    pregunta = (data.get("pregunta") or "").strip()
    if not pregunta:
        return jsonify({"error": "Falta la pregunta"}), 400
    try:
        return jsonify({"respuesta": rag(pregunta)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(port=5000, debug=True, use_reloader=False)