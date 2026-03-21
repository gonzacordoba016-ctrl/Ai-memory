# memory/pdf_memory.py

import os
import pdfplumber
from infrastructure.vector_store import vector_store
from core.logger import logger

FILES_DIR = os.path.abspath("./agent_files")


def ingest_pdf(filename: str) -> str:
    """
    Lee un PDF de agent_files/, lo divide en chunks
    y los guarda en memoria vectorial.
    """
    path = os.path.join(FILES_DIR, filename)

    if not os.path.exists(path):
        return f"Archivo '{filename}' no encontrado en agent_files/."

    if not filename.lower().endswith(".pdf"):
        return "El archivo debe ser un PDF."

    try:
        chunks = _extract_chunks(path)

        if not chunks:
            return "El PDF no tiene texto extraíble."

        for i, chunk in enumerate(chunks):
            vector_store.store(chunk, metadata={
                "source": filename,
                "chunk": i,
                "type": "pdf"
            })

        logger.info(f"PDF ingerido: {filename} ({len(chunks)} chunks)")
        return f"PDF '{filename}' procesado correctamente. {len(chunks)} fragmentos indexados en memoria."

    except Exception as e:
        logger.error(f"Error ingiriendo PDF: {e}")
        return f"Error procesando el PDF: {e}"


def _extract_chunks(path: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Extrae texto del PDF y lo divide en chunks con overlap."""
    full_text = ""

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"

    if not full_text.strip():
        return []

    # Dividir en chunks con overlap para no perder contexto entre fragmentos
    words = full_text.split()
    chunks = []
    i = 0

    while i < len(words):
        chunk = " ".join(words[i:i + chunk_size])
        chunks.append(chunk)
        i += chunk_size - overlap

    return chunks