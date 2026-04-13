# api/server.py
# Punto de entrada del servidor FastAPI.
# La lógica de cada dominio vive en api/routers/.

from dotenv import load_dotenv
load_dotenv()  # sin override: Railway/sistema tiene prioridad sobre .env local

import os
import sys

# Log de diagnóstico: muestra el provider y key en uso al arrancar
_provider = os.getenv("LLM_PROVIDER", "ollama")
_key = os.getenv("OPENROUTER_API_KEY", "") or os.getenv("AETHERMIND_API_KEY", "")
print(f"[STARTUP] LLM_PROVIDER={_provider} | key prefix={_key[:15]}... | model={os.getenv('OPENROUTER_MODEL', os.getenv('OLLAMA_MODEL', '?'))}", flush=True)
print(f"[STARTUP] PORT={os.getenv('PORT', '8000')} | MEMORY_DB={os.getenv('MEMORY_DB_PATH', './database/memory.db')}", flush=True)

# Coleccionamos errores de startup para reportarlos en /api/health
_startup_errors: list[str] = []

try:
    from core.config import validate_config
    validate_config()
except Exception as e:
    msg = f"[WARNING] CONFIG: {e}"
    print(msg, flush=True)
    _startup_errors.append(msg)

import asyncio
from datetime import datetime
import httpx
import sqlite3

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

try:
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from api.limiter import limiter
    _slowapi_ok = True
except Exception as e:
    _startup_errors.append(f"slowapi import failed: {e}")
    _slowapi_ok = False

app = FastAPI(title="Stratum — Hardware Memory Engine")

# ── Rate limiting ─────────────────────────────────────────────────────
if _slowapi_ok:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

# ── CORS ──────────────────────────────────────────────────────────────
try:
    from core.config import ALLOWED_ORIGINS
except Exception:
    ALLOWED_ORIGINS = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

try:
    app.mount("/static", StaticFiles(directory="api/static"), name="static")
except Exception as e:
    _startup_errors.append(f"static mount failed: {e}")

# ── Routers — cada uno en su propio try/except ────────────────────────
_routers_loaded: list[str] = []
_routers_failed: list[str] = []

def _include(name: str, import_path: str, mod_attr: str = "router"):
    try:
        import importlib
        mod = importlib.import_module(import_path)
        app.include_router(getattr(mod, mod_attr))
        _routers_loaded.append(name)
    except Exception as e:
        msg = f"Router '{name}' failed: {e}"
        print(f"[ERROR] {msg}", flush=True)
        _startup_errors.append(msg)
        _routers_failed.append(name)

_include("auth",             "api.routers.auth")
_include("memory",           "api.routers.memory")
_include("hardware",         "api.routers.hardware")
_include("hardware_bridge",  "api.routers.hardware_bridge")
_include("knowledge",        "api.routers.knowledge")
_include("circuits",         "api.routers.circuits")
_include("websockets",       "api.routers.websockets")
_include("intelligence",     "api.routers.intelligence")
_include("push",             "api.routers.push")
_include("schematics",       "api.routers.schematics")
_include("stock",            "api.routers.stock")
_include("decisions",        "api.routers.decisions")
_include("calc",             "api.routers.calc")

print(f"[STARTUP] Routers OK: {_routers_loaded}", flush=True)
if _routers_failed:
    print(f"[STARTUP] Routers FAILED: {_routers_failed}", flush=True)


# ── Lifecycle ─────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    _prov = os.getenv("LLM_PROVIDER", "ollama")
    _model = os.getenv("OPENROUTER_MODEL") or os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
    print(f"[Server] LLM provider={_prov} | model={_model}", flush=True)

    # Inyectar event loop en hardware bridge
    try:
        from api.routers import hardware_bridge
        hardware_bridge.set_event_loop(asyncio.get_event_loop())
    except Exception as e:
        _startup_errors.append(f"hardware_bridge.set_event_loop failed: {e}")

    # Inicializar tablas SQLite (ligero, rápido)
    try:
        from database.design_decisions import get_decisions_db
        from database.component_stock import get_stock_db
        get_decisions_db()
        get_stock_db()
        print("[Server] Tablas design_decisions y component_stock inicializadas.", flush=True)
    except Exception as e:
        _startup_errors.append(f"DB init failed: {e}")
        print(f"[Server] DB init error: {e}", flush=True)

    # Job worker
    try:
        from api.job_worker import job_worker_loop
        asyncio.create_task(job_worker_loop())
        print("[Server] Job worker iniciado.", flush=True)
    except Exception as e:
        _startup_errors.append(f"job_worker failed: {e}")
        print(f"[Server] Job worker error: {e}", flush=True)

    # AgentController y ProactiveEngine — en background para no bloquear el startup.
    # Uvicorn ya está escuchando el puerto y puede responder al healthcheck
    # mientras estos componentes se inicializan.
    asyncio.create_task(_init_agents_background())

    print(f"[Server] READY. Inicialización de agentes en background. Startup errors: {len(_startup_errors)}", flush=True)
    if _startup_errors:
        for e in _startup_errors:
            print(f"  - {e}", flush=True)


async def _init_agents_background():
    """Inicializa AgentController y ProactiveEngine en background task.
    Corre después de que uvicorn ya está escuchando el puerto,
    así el healthcheck puede pasar mientras se inicializa."""
    import api.app_state as _state

    try:
        from agent.agent_controller import AgentController
        _state.agent = AgentController()
        print("[STARTUP] AgentController inicializado.", flush=True)
    except Exception as e:
        msg = f"AgentController init failed: {e}"
        print(f"[ERROR] {msg}", flush=True)
        _startup_errors.append(msg)

    try:
        from agent.proactive_engine import ProactiveEngine
        _state.proactive_engine = ProactiveEngine()
        await _state.proactive_engine.start()
        print("[STARTUP] ProactiveEngine iniciado.", flush=True)
    except Exception as e:
        msg = f"ProactiveEngine init failed: {e}"
        print(f"[ERROR] {msg}", flush=True)
        _startup_errors.append(msg)


@app.on_event("shutdown")
async def shutdown_event():
    try:
        from llm.async_client import close
        await close()
    except Exception:
        pass


# ── Frontend ──────────────────────────────────────────────────────────

@app.get("/")
async def root():
    try:
        return FileResponse("api/static/index.html")
    except Exception:
        return JSONResponse({"status": "ok", "message": "Stratum running"})


# ── Health check ──────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    try:
        from core.config import SQL_DB_PATH, OLLAMA_BASE_URL
    except Exception:
        SQL_DB_PATH = "./database/memory.db"
        OLLAMA_BASE_URL = "http://localhost:11434"

    checks: dict = {}

    # SQLite
    try:
        conn = sqlite3.connect(SQL_DB_PATH, timeout=2)
        conn.execute("SELECT 1")
        conn.close()
        checks["sqlite"] = "ok"
    except Exception as e:
        checks["sqlite"] = f"error: {e}"

    # Qdrant
    try:
        from infrastructure.vector_store import vector_store
        if vector_store.client:
            vector_store.client.get_collections()
            checks["qdrant"] = "ok"
        else:
            checks["qdrant"] = "disabled"
    except Exception as e:
        checks["qdrant"] = f"error: {e}"

    # LLM (solo si provider es ollama — openrouter no tiene endpoint /api/tags)
    provider = os.getenv("LLM_PROVIDER", "ollama")
    if provider == "ollama":
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
                checks["ollama"] = "ok" if r.status_code == 200 else f"http {r.status_code}"
        except Exception as e:
            checks["ollama"] = f"error: {e}"
    else:
        checks["llm_provider"] = provider

    overall = "ok" if checks.get("sqlite") == "ok" else "degraded"

    return {
        "status":         overall,
        "services":       checks,
        "startup_errors": _startup_errors,
        "routers_ok":     _routers_loaded,
        "routers_failed": _routers_failed,
        "timestamp":      datetime.utcnow().isoformat(),
    }


# ── Arranque directo ──────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)
