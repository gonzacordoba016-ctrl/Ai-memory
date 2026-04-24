# knowledge/knowledge_base.py
#
# Sistema de knowledge base unificado.
# Indexa .txt, .md y .pdf de agent_files/knowledge/
# y expone búsqueda semántica sobre ese contenido.

import os
from pathlib import Path
from datetime import datetime, timezone
from infrastructure.vector_store import vector_store
from infrastructure.embeddings import embedding_model
from core.logger import logger

KNOWLEDGE_DIR = os.path.abspath("./agent_files/knowledge")
CHUNK_SIZE    = 400   # palabras por chunk
OVERLAP       = 50    # palabras de overlap entre chunks


# ======================
# CHUNKING
# ======================

def _chunk_text(text: str, source: str) -> list[dict]:
    """Divide texto en chunks con overlap."""
    words  = text.split()
    chunks = []
    i      = 0
    idx    = 0

    while i < len(words):
        chunk = " ".join(words[i:i + CHUNK_SIZE])
        if chunk.strip():
            chunks.append({
                "content": chunk,
                "source":  source,
                "chunk":   idx,
            })
        i   += CHUNK_SIZE - OVERLAP
        idx += 1

    return chunks


# ======================
# LOADERS
# ======================

def _load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def _load_pdf(path: str) -> str:
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(str(t))
        return "\n".join(text_parts) + "\n" if text_parts else ""
    except ImportError:
        try:
            from pypdf import PdfReader
            reader = PdfReader(path)
            return "\n".join(
                page.extract_text() or ""
                for page in reader.pages
            )
        except Exception as e:
            logger.error(f"Error leyendo PDF {path}: {e}")
            return ""


def _load_file(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return _load_pdf(path)
    return _load_text(path)


# ======================
# INDEXACIÓN
# ======================

def index_knowledge_base(force: bool = False) -> dict:
    """
    Indexa todos los documentos en agent_files/knowledge/.
    Si force=False, solo indexa archivos nuevos (no reindexar).
    Retorna estadísticas: archivos procesados, chunks indexados.
    """
    os.makedirs(KNOWLEDGE_DIR, exist_ok=True)

    supported = {".txt", ".md", ".pdf"}
    files     = [
        p for p in Path(KNOWLEDGE_DIR).rglob("*")
        if p.suffix.lower() in supported and p.is_file()
    ]

    if not files:
        logger.info("[Knowledge] No hay documentos para indexar")
        return {"files": 0, "chunks": 0}

    # Obtener fuentes ya indexadas para no duplicar
    indexed_sources = set()
    if not force:
        try:
            points, _ = vector_store.client.scroll(
                collection_name=vector_store.collection,
                scroll_filter=None,
                limit=10000,
                with_payload=True,
            )
            for point in points:
                src = (point.payload or {}).get("source", "")
                ktype = (point.payload or {}).get("type", "")
                if ktype == "knowledge":
                    indexed_sources.add(src)
        except Exception:
            pass

    total_chunks = 0
    total_files  = 0

    for filepath in files:
        source = filepath.name

        if source in indexed_sources:
            logger.info(f"[Knowledge] Ya indexado: {source} — saltando")
            continue

        logger.info(f"[Knowledge] Indexando: {source}")
        text = _load_file(str(filepath))

        if not text.strip():
            logger.warning(f"[Knowledge] Sin texto: {source}")
            continue

        chunks = _chunk_text(text, source)

        for chunk in chunks:
            vector_store.store(
                chunk["content"],
                metadata={
                    "type":       "knowledge",
                    "source":     source,
                    "chunk":      chunk["chunk"],
                    "indexed_at": datetime.now(timezone.utc).isoformat(),
                }
            )

        total_chunks += len(chunks)
        total_files  += 1
        logger.info(f"[Knowledge] {source}: {len(chunks)} chunks")

    logger.info(f"[Knowledge] Indexación completa: {total_files} archivos, {total_chunks} chunks")
    return {"files": total_files, "chunks": total_chunks}


def search_knowledge(query: str, top_k: int = 4) -> list[str]:
    """
    Busca en la knowledge base.
    Retorna lista de textos relevantes con su fuente.
    """
    results = vector_store.search(query, top_k=top_k * 2)

    # Filtrar solo resultados de tipo knowledge
    knowledge_results = [
        r for r in results
        if isinstance(r, dict) and r.get("metadata", {}).get("type") == "knowledge"
    ]

    if not knowledge_results:
        return []

    output = []
    for r in knowledge_results[:top_k]:
        source = r.get("metadata", {}).get("source", "desconocido")
        text   = r.get("text", "")
        output.append(f"[{source}] {text}")

    return output


def list_indexed_documents() -> list[dict]:
    """Lista los documentos actualmente indexados con estadísticas."""
    try:
        points, _ = vector_store.client.scroll(
            collection_name=vector_store.collection,
            scroll_filter=None,
            limit=10000,
            with_payload=True,
        )
        sources: dict = {}
        for point in points:
            payload = point.payload or {}
            if payload.get("type") != "knowledge":
                continue
            src = payload.get("source", "desconocido")
            if src not in sources:
                sources[src] = {"source": src, "chunks": 0, "indexed_at": payload.get("indexed_at")}
            sources[src]["chunks"] = int(sources[src]["chunks"]) + 1

        return list(sources.values())
    except Exception as e:
        logger.error(f"[Knowledge] Error listando documentos: {e}")
        return []