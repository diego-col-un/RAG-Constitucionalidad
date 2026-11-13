import os
import numpy as np
import requests
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()


def llamar_llm(messages, model="deepseek/deepseek-chat"):
    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
            "HTTP-Referer": "http://localhost",
            "X-Title": "RAG Constitucion PDF",
        },
        json={"model": model, "messages": messages, "temperature": 0.1},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


# Modelo multilingüe (el documento está en español)
embedder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")


# 2. Carga del PDF y fragmentación por palabras con solapamiento
def cargar_y_fragmentar_pdf(ruta_pdf, tam_chunk=200, solape=40):
    if not os.path.exists(ruta_pdf):
        raise FileNotFoundError(f"No se encontró el archivo: {ruta_pdf}")

    reader = PdfReader(ruta_pdf)
    chunks = []
    for num_pagina, pagina in enumerate(reader.pages, start=1):
        texto = pagina.extract_text() or ""
        palabras = texto.split()
        paso = tam_chunk - solape
        for i in range(0, len(palabras), paso):
            fragmento = " ".join(palabras[i:i + tam_chunk])
            if fragmento:
                chunks.append(f"[Pág. {num_pagina}] {fragmento}")

    if not chunks:
        raise ValueError(
            "No se extrajo texto. Si el PDF es escaneado (imágenes), necesitas OCR."
        )
    return chunks


# 3. Función RAG (Retrieval + Generation)
def rag_openrouter(pregunta, chunks, chunk_embeddings, top_k=5):
    query_emb = embedder.encode(pregunta, normalize_embeddings=True)

    # Con embeddings normalizados, el producto punto = similitud coseno
    similitudes = chunk_embeddings @ query_emb
    top_indices = np.argsort(similitudes)[::-1][:top_k]
    contexto = "\n\n".join(chunks[i] for i in top_indices)

    prompt = f"""Responde a la pregunta únicamente con base en el siguiente contexto recuperado del documento.
Si la respuesta no está en el contexto, dilo claramente. Cita la página cuando sea posible.

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


# 4. Ejecución
if __name__ == "__main__":
    RUTA_DOCUMENTO = os.path.join("Data", "constitucio-politica-colombia-1991.pdf")

    print(f"Cargando '{RUTA_DOCUMENTO}'...")
    chunks = cargar_y_fragmentar_pdf(RUTA_DOCUMENTO)
    chunk_embeddings = embedder.encode(
        chunks, normalize_embeddings=True, show_progress_bar=True
    )
    print(f"Documento indexado correctamente ({len(chunks)} fragmentos).\n")

    pregunta = "¿Qué dice la Constitución sobre la acción de tutela?"
    respuesta = rag_openrouter(pregunta, chunks, chunk_embeddings)

    print(f"Pregunta: {pregunta}\n")
    print(f"Respuesta:\n{respuesta}")