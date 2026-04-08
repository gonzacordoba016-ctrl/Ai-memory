# api/routers/knowledge.py
# Endpoints de knowledge base: listado, indexación, búsqueda semántica

import asyncio
from fastapi import APIRouter, Request
from knowledge.knowledge_base import index_knowledge_base, search_knowledge, list_indexed_documents
from api.limiter import limiter

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("/documents")
async def get_knowledge_documents():
    docs = list_indexed_documents()
    return {"documents": docs, "total": len(docs)}


@router.post("/index")
@limiter.limit("2/minute")
async def trigger_index(request: Request, force: bool = False):
    result = await asyncio.to_thread(index_knowledge_base, force=force)
    return {"status": "ok", "indexed": result}


@router.get("/search")
async def knowledge_search(q: str, top_k: int = 5):
    results = search_knowledge(q, top_k=top_k)
    return {"query": q, "results": results}
