# api/routers/knowledge.py
# Endpoints de knowledge base: listado, indexación, búsqueda semántica, upload

import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from api.auth import get_current_user
from knowledge.knowledge_base import index_knowledge_base, search_knowledge, list_indexed_documents
from api.limiter import limiter
from core.logger import logger

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"], dependencies=[Depends(get_current_user)])

_KB_DIR = Path("agent_files/knowledge")
_ALLOWED_EXTS = {".txt", ".md", ".pdf", ".py", ".c", ".cpp", ".h", ".json", ".yaml", ".yml"}
_MAX_SIZE = 5 * 1024 * 1024  # 5 MB


@router.get("/documents")
async def get_knowledge_documents():
    docs = list_indexed_documents()
    return {"documents": docs, "total": len(docs)}


@router.post("/upload")
async def upload_knowledge_document(file: UploadFile = File(...)):
    """Sube un archivo a agent_files/knowledge/ y lo indexa inmediatamente."""
    suffix = Path(file.filename or "file.txt").suffix.lower()
    if suffix not in _ALLOWED_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Extensión '{suffix}' no permitida. Permitidas: {', '.join(sorted(_ALLOWED_EXTS))}",
        )

    content = await file.read()
    if len(content) > _MAX_SIZE:
        raise HTTPException(status_code=413, detail="Archivo demasiado grande (máx 5 MB)")

    _KB_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "upload.txt").name
    dest = _KB_DIR / safe_name
    dest.write_bytes(content)
    logger.info(f"[Knowledge] Archivo subido: {safe_name} ({len(content)} bytes)")

    # Indexar solo el archivo nuevo
    indexed = await asyncio.to_thread(index_knowledge_base, force=False)
    return {"status": "ok", "filename": safe_name, "size": len(content), "indexed": indexed}


@router.post("/index")
@limiter.limit("2/minute")
async def trigger_index(request: Request, force: bool = False):
    result = await asyncio.to_thread(index_knowledge_base, force=force)
    return {"status": "ok", "indexed": result}


@router.get("/search")
async def knowledge_search(q: str, top_k: int = 5):
    results = search_knowledge(q, top_k=top_k)
    return {"query": q, "results": results}


@router.delete("/delete/{filename}")
async def delete_knowledge_document(filename: str):
    """Elimina un archivo de agent_files/knowledge/ y re-indexa."""
    safe_name = Path(filename).name
    if not safe_name or safe_name != filename:
        raise HTTPException(status_code=400, detail="Nombre de archivo inválido")

    target = _KB_DIR / safe_name
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Archivo '{safe_name}' no encontrado")

    target.unlink()
    logger.info(f"[Knowledge] Archivo eliminado: {safe_name}")

    indexed = await asyncio.to_thread(index_knowledge_base, force=True)
    return {"status": "ok", "deleted": safe_name, "indexed": indexed}
