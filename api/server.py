# api/server.py
# Punto de entrada del servidor FastAPI.
# La lógica de cada dominio vive en api/routers/.

from dotenv import load_dotenv
load_dotenv(override=True)  # .env local tiene prioridad; Railway no usa .env

import os
import sys
import logging

# Logger de servidor — centraliza todos los mensajes de startup/runtime
_log = logging.getLogger("stratum.server")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Log de diagnóstico: muestra el provider y key en uso al arrancar
_provider = os.getenv("LLM_PROVIDER", "ollama")
_key = os.getenv("OPENROUTER_API_KEY", "")
_log.info(f"[STARTUP] LLM_PROVIDER={_provider} | key prefix={_key[:15]}... | model={os.getenv('OPENROUTER_MODEL', os.getenv('OLLAMA_MODEL', '?'))}")
_log.info(f"[STARTUP] PORT={os.getenv('PORT', '8000')} | MEMORY_DB={os.getenv('MEMORY_DB_PATH', './database/memory.db')}")

# Coleccionamos errores de startup para reportarlos en /api/health
_startup_errors: list[str] = []

# Timestamp de arranque — usado por el cliente WS para detectar reinicios del server
import time as _time
SERVER_START_TS: int = int(_time.time())

try:
    from core.config import validate_config
    validate_config()
except Exception as e:
    msg = f"[WARNING] CONFIG: {e}"
    _log.warning(msg)
    _startup_errors.append(msg)

import asyncio
from datetime import datetime, timezone
import httpx
import sqlite3

from fastapi import Depends, FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from api.auth import get_current_user

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

# Compresión GZip — solo aplica a respuestas HTTP (no WebSocket)
app.add_middleware(GZipMiddleware, minimum_size=1000)

try:
    app.mount("/static", StaticFiles(directory="api/static"), name="static")
except Exception as e:
    _startup_errors.append(f"static mount failed: {e}")

# ── Routers — cada uno en su propio try/except ────────────────────────
_routers_loaded: list[str] = []
_routers_failed: list[str] = []

_AUTH_DEP = [Depends(get_current_user)]

def _include(name: str, import_path: str, mod_attr: str = "router", protected: bool = False):
    try:
        import importlib
        mod = importlib.import_module(import_path)
        deps = _AUTH_DEP if protected else []
        app.include_router(getattr(mod, mod_attr), dependencies=deps)
        _routers_loaded.append(name)
    except Exception as e:
        msg = f"Router '{name}' failed: {e}"
        print(f"[ERROR] {msg}", flush=True)
        _startup_errors.append(msg)
        _routers_failed.append(name)

# public: auth (login/register), circuits-public (share links), websockets (own auth)
_include("auth",             "api.routers.auth")
_include("circuits-public",  "api.routers.circuits", "_public_router")
_include("websockets",       "api.routers.websockets")
# already protected at router level — redundant dep is harmless
_include("memory",           "api.routers.memory",          protected=True)
_include("circuits",         "api.routers.circuits",        protected=True)
_include("knowledge",        "api.routers.knowledge",       protected=True)
_include("projects",         "api.routers.projects",        protected=True)
# newly protected
_include("hardware",         "api.routers.hardware",        protected=True)
_include("hardware_bridge",  "api.routers.hardware_bridge", protected=True)
_include("intelligence",     "api.routers.intelligence",    protected=True)
_include("push",             "api.routers.push",            protected=True)
_include("schematics",       "api.routers.schematics",      protected=True)
_include("stock",            "api.routers.stock",           protected=True)
_include("decisions",        "api.routers.decisions",       protected=True)
_include("calc",             "api.routers.calc",            protected=True)
_include("hardware_state",   "api.routers.hardware_state",  protected=True)

_log.info(f"[STARTUP] Routers OK: {_routers_loaded}")
if _routers_failed:
    _log.warning(f"[STARTUP] Routers FAILED: {_routers_failed}")


# ── Lifecycle ─────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    _prov = os.getenv("LLM_PROVIDER", "ollama")
    _model = os.getenv("OPENROUTER_MODEL") or os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
    _log.info(f"[Server] LLM provider={_prov} | model={_model}")

    # Inyectar event loop en hardware bridge
    try:
        from api.routers import hardware_bridge
        hardware_bridge.set_event_loop(asyncio.get_running_loop())
    except Exception as e:
        _startup_errors.append(f"hardware_bridge.set_event_loop failed: {e}")

    # Inicializar tablas SQLite (ligero, rápido)
    try:
        from database.design_decisions import get_decisions_db
        from database.component_stock import get_stock_db
        get_decisions_db()
        get_stock_db()
        _log.info("[Server] Tablas design_decisions y component_stock inicializadas.")
    except Exception as e:
        _startup_errors.append(f"DB init failed: {e}")
        _log.error(f"[Server] DB init error: {e}")

    # Job worker
    try:
        from api.job_worker import job_worker_loop
        asyncio.create_task(job_worker_loop())
        _log.info("[Server] Job worker iniciado.")
    except Exception as e:
        _startup_errors.append(f"job_worker failed: {e}")
        _log.error(f"[Server] Job worker error: {e}")

    # AgentController y ProactiveEngine — en background para no bloquear el startup.
    asyncio.create_task(_init_agents_background())

    _log.info(f"[Server] READY. Startup errors: {len(_startup_errors)}")
    for err_msg in _startup_errors:
        _log.warning(f"  - {err_msg}")


async def _init_agents_background():
    """Inicializa AgentController y ProactiveEngine en background task.
    Corre después de que uvicorn ya está escuchando el puerto,
    así el healthcheck puede pasar mientras se inicializa."""
    import api.app_state as _state

    try:
        from agent.agent_controller import AgentController
        _state.agent = AgentController()
        _log.info("[STARTUP] AgentController inicializado.")
    except Exception as e:
        msg = f"AgentController init failed: {e}"
        _log.error(f"[ERROR] {msg}")
        _startup_errors.append(msg)

    try:
        from agent.proactive_engine import ProactiveEngine
        _state.proactive_engine = ProactiveEngine()
        await _state.proactive_engine.start()
        _log.info("[STARTUP] ProactiveEngine iniciado.")
    except Exception as e:
        msg = f"ProactiveEngine init failed: {e}"
        _log.error(f"[ERROR] {msg}")
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

@app.get("/health")
async def health_root():
    """Healthcheck raíz para Railway y proxies que no usan /api prefix."""
    return JSONResponse(status_code=200, content={"status": "ok"})


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

    # Qdrant — lazy/opcional: "not_initialized" no es un fallo
    try:
        from infrastructure.vector_store import vector_store
        if vector_store.client:
            vector_store.client.get_collections()
            checks["qdrant"] = "ok"
        else:
            checks["qdrant"] = "not_initialized"
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

    # Solo SQLite determina el estado general — Qdrant es lazy y opcional
    overall = "ok" if checks.get("sqlite") == "ok" else "degraded"

    return JSONResponse(
        status_code=200,
        content={
            "status":         overall,
            "services":       checks,
            "startup_errors": _startup_errors,
            "routers_ok":     _routers_loaded,
            "routers_failed": _routers_failed,
            "timestamp":      datetime.now(timezone.utc).isoformat(),
        },
    )


# ── Arranque directo ──────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)
