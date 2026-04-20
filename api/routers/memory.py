# api/routers/memory.py
# Endpoints de memoria: facts, historial, búsqueda semántica, grafo, perfil, plugins, stats

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse
from datetime import datetime
from pydantic import BaseModel

from api.auth import get_current_user
from database.sql_memory import _default as sql_db
from memory.vector_memory import search_memory, search_memory_with_scores
from memory.graph_memory import graph_memory
from database.hardware_memory import hardware_memory

router = APIRouter(tags=["memory"], dependencies=[Depends(get_current_user)])


@router.get("/api/debug/agent")
async def debug_agent_state():
    import api.app_state as _state
    return {"agent_ready": _state.agent is not None, "agent_type": type(_state.agent).__name__ if _state.agent else None}


@router.get("/api/stats")
async def get_stats():
    facts    = sql_db.get_all_facts()
    messages = sql_db.get_recent_messages(1000)
    g_stats  = graph_memory.stats()
    hw_stats = hardware_memory.get_stats()
    return {
        "facts_count":    len(facts),
        "messages_count": len(messages),
        "graph_nodes":    g_stats["nodes"],
        "graph_edges":    g_stats["edges"],
        "hw_devices":     hw_stats["devices"],
        "hw_flashes":     hw_stats["total_flashes"],
        "hw_circuits":    hw_stats.get("circuits", 0),
        "timestamp":      datetime.now().isoformat(),
    }


@router.get("/api/facts")
async def get_facts():
    return {"facts": sql_db.get_all_facts()}


@router.get("/api/history")
async def get_history(limit: int = 50, session_id: str = None):
    if session_id:
        messages = sql_db.get_conversation_by_session(session_id, limit=limit)
    else:
        messages = sql_db.get_recent_messages(limit=limit)
    return {"messages": messages}


@router.get("/api/search")
async def memory_search(q: str, top_k: int = 5):
    combined: list[dict] = []

    # Memoria del chat (con scores)
    try:
        mem = search_memory_with_scores(q, top_k=top_k)
        combined.extend(mem)
    except Exception:
        pass

    # Knowledge base
    try:
        from knowledge.knowledge_base import search_knowledge
        kb = search_knowledge(q, top_k=top_k)
        for text in kb:
            combined.append({"text": text, "score": 0.75, "metadata": {"type": "knowledge"}})
    except Exception:
        pass

    combined.sort(key=lambda x: x.get("score", 0), reverse=True)
    return {"query": q, "results": combined[:top_k]}


@router.get("/api/graph")
async def get_graph():
    return {
        "relations": graph_memory.get_all_relations(),
        "stats":     graph_memory.stats(),
    }


@router.get("/api/agents/status")
async def agents_status():
    return {
        "agents": [
            {"name": "ResearchAgent",  "description": "Búsqueda web y knowledge base"},
            {"name": "CodeAgent",      "description": "Ejecución de código Python"},
            {"name": "MemoryAgent",    "description": "Consulta de memoria"},
            {"name": "HardwareAgent",  "description": "Programación de hardware"},
            {"name": "CircuitAgent",   "description": "Parseo y diseño de circuitos"},
            {"name": "Orchestrator",   "description": "Coordinador central"},
        ]
    }


@router.get("/api/plugins")
async def get_plugins():
    from tools.plugin_loader import plugin_loader
    info = plugin_loader.get_plugins_info()
    return {"plugins": info, "total": len(info)}


@router.post("/api/plugins/install")
async def install_plugin(file: UploadFile = File(...)):
    """
    Instala un plugin desde un archivo ZIP.

    El ZIP debe contener:
      - plugin.json  (manifesto con name, version, description, entry, permissions)
      - <entry>.py   (código del plugin con PLUGIN_NAME, PLUGIN_DESCRIPTION, PLUGIN_TOOLS)
    """
    from tools.plugin_loader import plugin_loader

    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="El archivo debe ser un ZIP")

    zip_bytes = await file.read()
    result    = plugin_loader.install_from_zip(zip_bytes)

    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@router.delete("/api/plugins/{name}")
async def uninstall_plugin(name: str):
    """Desinstala un plugin por nombre. Elimina sus archivos y lo desregistra en caliente."""
    from tools.plugin_loader import plugin_loader

    result = plugin_loader.uninstall(name)
    if result["status"] == "error":
        raise HTTPException(status_code=404, detail=result["message"])

    return result


@router.get("/api/profile")
async def get_user_profile():
    import api.app_state as _state
    from fastapi import HTTPException
    if _state.agent is None:
        raise HTTPException(status_code=503, detail="Agente inicializándose, intentá en unos segundos")
    return {"profile": _state.agent.profiler.get_profile_summary()}


@router.delete("/api/profile")
async def reset_user_profile():
    import api.app_state as _state
    from fastapi import HTTPException
    if _state.agent is None:
        raise HTTPException(status_code=503, detail="Agente inicializándose, intentá en unos segundos")
    _state.agent.profiler._save_profile(_state.agent.profiler._default_profile())
    _state.agent.profiler._cache = None
    return {"status": "reset"}


# ── Jobs ─────────────────────────────────────────────────────────────

@router.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    from api.app_state import jobs
    from fastapi import HTTPException
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    return {k: v for k, v in job.items() if not k.startswith("_")}


@router.get("/api/jobs")
async def list_jobs():
    from api.app_state import jobs
    return {
        "jobs": [
            {k: v for k, v in j.items() if not k.startswith("_")}
            for j in jobs.values()
        ],
        "total": len(jobs),
    }


@router.get("/api/cache/stats")
async def cache_stats():
    """Estado del semantic cache de LLM (hits, entradas activas, config)."""
    try:
        from llm.cache import llm_cache
        return {"status": "ok", **llm_cache.stats()}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.post("/api/cache/clear")
async def cache_clear():
    """Limpia el semantic cache de LLM manualmente."""
    try:
        from llm.cache import llm_cache
        llm_cache.clear()
        return {"status": "ok", "message": "Cache limpiado"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


# ── Chat Sessions ─────────────────────────────────────────────────────────────

class SessionCreateRequest(BaseModel):
    title: str = "Nueva conversación"

class SessionTitleRequest(BaseModel):
    title: str


@router.get("/api/sessions")
async def list_sessions():
    sessions = sql_db.list_sessions()
    return JSONResponse(content={"sessions": sessions})


@router.post("/api/sessions", status_code=201)
async def create_session(body: SessionCreateRequest = None):
    import uuid
    sid = str(uuid.uuid4())
    title = body.title if body else "Nueva conversación"
    result = sql_db.create_session(session_id=sid, title=title)
    return JSONResponse(content=result, status_code=201)


@router.patch("/api/sessions/{session_id}/title")
async def rename_session(session_id: str, body: SessionTitleRequest):
    sql_db.update_session_title(session_id, body.title.strip()[:80] or "Sin título")
    return {"ok": True}


@router.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    sql_db.delete_session(session_id)
    return {"ok": True}


@router.get("/api/sessions/{session_id}/export")
async def export_session(session_id: str):
    """Exporta la sesión como ZIP con: chat.md, firmware.cpp (si hay), decisiones.md"""
    import io
    import zipfile
    from database.sql_memory import SQLMemory
    db = SQLMemory()
    msgs = db.get_conversation_by_session(session_id, limit=500)
    if not msgs:
        raise HTTPException(status_code=404, detail="Sesión no encontrada o vacía")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # chat.md
        chat_lines = [f"# Stratum — Sesión {session_id[:8]}\n", f"Exportado: {datetime.utcnow().isoformat()}\n\n"]
        firmware_blocks = []
        for m in msgs:
            role = "**Usuario**" if m["role"] == "user" else "**Agente**"
            chat_lines.append(f"---\n{role}\n\n{m['content']}\n\n")
            # Extraer bloques de firmware C++
            if m["role"] == "assistant" and ("void setup()" in m["content"] or "```cpp" in m["content"]):
                import re
                blocks = re.findall(r'```(?:cpp|c|arduino)?\n(.*?)```', m["content"], re.DOTALL)
                firmware_blocks.extend(blocks)
        zf.writestr("chat.md", "".join(chat_lines))

        # firmware.cpp (último bloque encontrado)
        if firmware_blocks:
            zf.writestr("firmware.cpp", firmware_blocks[-1])

        # decisiones.md
        try:
            from database.design_decisions import get_decisions_db
            decisions = get_decisions_db().get_all(limit=50)
            if decisions:
                dec_lines = ["# Decisiones de Diseño\n\n"]
                for d in decisions:
                    dec_lines.append(f"## [{d.get('project','—')}] {d.get('decision','')}\n")
                    if d.get('reasoning'):
                        dec_lines.append(f"_{d['reasoning']}_\n\n")
                zf.writestr("decisiones.md", "".join(dec_lines))
        except Exception:
            pass

    buf.seek(0)
    filename = f"stratum_{session_id[:8]}_{datetime.utcnow().strftime('%Y%m%d')}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
