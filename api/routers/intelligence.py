# api/routers/intelligence.py
# Endpoints para perfiles de IA y fuentes de conocimiento.

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional, List

from database.intelligence import intelligence_db
from core.logger import logger

router = APIRouter(tags=["intelligence"])


# ── Modelos Pydantic ──────────────────────────────────────────────────────────

class ProfileCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    system_prompt: str
    model_fast: Optional[str] = None
    model_smart: Optional[str] = None
    active_sources: Optional[List[str]] = []


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    model_fast: Optional[str] = None
    model_smart: Optional[str] = None
    active_sources: Optional[List[str]] = None


class SourceCreate(BaseModel):
    name: str
    type: str   # "text" | "url" | "file"
    content: Optional[str] = ""
    description: Optional[str] = ""


# ── Perfil activo ─────────────────────────────────────────────────────────────

@router.get("/api/intelligence/active")
async def get_active():
    """Retorna el perfil activo y sus fuentes habilitadas."""
    profile = intelligence_db.get_active_profile()
    if not profile:
        return {"profile": None, "sources": []}
    sources = []
    if profile.get("active_sources"):
        all_sources = {s["id"]: s for s in intelligence_db.list_sources()}
        sources = [all_sources[sid] for sid in profile["active_sources"] if sid in all_sources]
    return {"profile": profile, "sources": sources}


# ── Perfiles ──────────────────────────────────────────────────────────────────

@router.get("/api/intelligence/profiles")
async def list_profiles():
    return {"profiles": intelligence_db.list_profiles()}


@router.post("/api/intelligence/profiles")
async def create_profile(body: ProfileCreate):
    try:
        profile = intelligence_db.create_profile(body.dict())
        logger.info(f"[Intelligence] Perfil creado: {body.name}")
        return {"profile": profile}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.put("/api/intelligence/profiles/{profile_id}")
async def update_profile(profile_id: str, body: ProfileUpdate):
    data = {k: v for k, v in body.dict().items() if v is not None}
    profile = intelligence_db.update_profile(profile_id, data)
    if not profile:
        raise HTTPException(404, "Perfil no encontrado")
    return {"profile": profile}


@router.post("/api/intelligence/profiles/{profile_id}/activate")
async def activate_profile(profile_id: str):
    if not intelligence_db.get_profile(profile_id):
        raise HTTPException(404, "Perfil no encontrado")
    ok = intelligence_db.activate_profile(profile_id)
    if not ok:
        raise HTTPException(500, "Error activando perfil")
    logger.info(f"[Intelligence] Perfil activado: {profile_id}")
    return {"ok": True, "active_id": profile_id}


@router.delete("/api/intelligence/profiles/{profile_id}")
async def delete_profile(profile_id: str):
    if not intelligence_db.delete_profile(profile_id):
        raise HTTPException(400, "No se puede eliminar este perfil (es de sistema o el único existente)")
    return {"ok": True}


# ── Fuentes de conocimiento ───────────────────────────────────────────────────

@router.get("/api/intelligence/sources")
async def list_sources():
    return {"sources": intelligence_db.list_sources()}


@router.post("/api/intelligence/sources")
async def create_source(body: SourceCreate):
    source = intelligence_db.create_source(body.dict())
    logger.info(f"[Intelligence] Fuente creada: {body.name} ({body.type})")
    return {"source": source}


@router.post("/api/intelligence/sources/{source_id}/index")
async def index_source(source_id: str):
    """Vectoriza el contenido de la fuente en Qdrant."""
    source = intelligence_db.get_source(source_id)
    if not source:
        raise HTTPException(404, "Fuente no encontrada")
    if not source.get("content", "").strip():
        raise HTTPException(400, "La fuente no tiene contenido para indexar")
    try:
        from knowledge.knowledge_base import _chunk_text
        from infrastructure.vector_store import vector_store
        from datetime import datetime, timezone

        chunks = _chunk_text(source["content"], source["name"])
        for chunk in chunks:
            vector_store.store(
                chunk["content"],
                metadata={
                    "type":       "knowledge_source",
                    "source":     source["name"],
                    "source_id":  source_id,
                    "chunk":      chunk["chunk"],
                    "indexed_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        intelligence_db.mark_indexed(source_id)
        logger.info(f"[Intelligence] Fuente indexada: {source['name']} — {len(chunks)} chunks")
        return {"ok": True, "chunks": len(chunks)}
    except Exception as e:
        logger.error(f"[Intelligence] Error indexando fuente {source_id}: {e}")
        raise HTTPException(500, f"Error indexando: {e}")


@router.delete("/api/intelligence/sources/{source_id}")
async def delete_source(source_id: str):
    if not intelligence_db.delete_source(source_id):
        raise HTTPException(404, "Fuente no encontrada")
    return {"ok": True}
