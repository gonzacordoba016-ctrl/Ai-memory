# api/server.py
# Punto de entrada del servidor FastAPI.
# La lógica de cada dominio vive en api/routers/.

from dotenv import load_dotenv
load_dotenv(override=True)  # override=True: el .env pisa variables de sistema/sesión

import os
os.environ["AETHERMIND_AGENT_ID"] = "56dd50bb-dba1-42fc-b46a-d9cefa170500"
os.environ["AETHERMIND_ENV"]      = "development"

# Log de diagnóstico: muestra el provider y key en uso al arrancar
_provider = os.getenv("LLM_PROVIDER", "ollama")
_key = os.getenv("OPENROUTER_API_KEY", "") or os.getenv("AETHERMIND_API_KEY", "")
print(f"[STARTUP] LLM_PROVIDER={_provider} | key prefix={_key[:15]}... | model={os.getenv('OPENROUTER_MODEL', os.getenv('OLLAMA_MODEL', '?'))}")

from core.config import validate_config
try:
    validate_config()
except (EnvironmentError, ValueError) as e:
    print(f"\n❌ ERROR DE CONFIGURACIÓN:\n{e}\n")
    exit(1)

import asyncio
from datetime import datetime
import httpx
import sqlite3

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from api.app_state import agent, proactive_engine  # noqa: F401 — inicializa singletons
from api.routers import memory, hardware, knowledge, circuits, websockets, auth, intelligence, push, hardware_bridge
from api.limiter import limiter
from core.logger import logger

app = FastAPI(title="Stratum — Hardware Memory Engine")

# ── Rate limiting ────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# ── CORS ─────────────────────────────────────────────────────────────
from core.config import ALLOWED_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.mount("/static", StaticFiles(directory="api/static"), name="static")


# ── Lifecycle ────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    from core.config import LLM_API, LLM_MODEL, PROVIDER
    logger.info(f"[Server] LLM provider={PROVIDER} | url={LLM_API} | model={LLM_MODEL}")

    # Inyectar el event loop en el hardware bridge para calls sync desde threads
    hardware_bridge.set_event_loop(asyncio.get_event_loop())

    await proactive_engine.start()
    logger.info("[Server] Motor proactivo iniciado.")

    from api.job_worker import job_worker_loop
    asyncio.create_task(job_worker_loop())
    logger.info("[Server] Job worker iniciado.")


@app.on_event("shutdown")
async def shutdown_event():
    from llm.async_client import close
    await close()
    logger.info("[Server] Cliente async cerrado.")


# ── Frontend ─────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse("api/static/index.html")


# ── Health check extendido ───────────────────────────────────────────

@app.get("/api/health")
async def health():
    from core.config import SQL_DB_PATH, OLLAMA_BASE_URL

    checks: dict = {}

    # SQLite
    try:
        conn = sqlite3.connect(SQL_DB_PATH, timeout=2)
        conn.execute("SELECT 1")
        conn.close()
        checks["sqlite"] = "ok"
    except Exception as e:
        checks["sqlite"] = f"error: {e}"

    # Qdrant (vector store)
    try:
        from infrastructure.vector_store import vector_store
        vector_store.client.get_collections()
        checks["qdrant"] = "ok"
    except Exception as e:
        checks["qdrant"] = f"error: {e}"

    # Ollama / LLM proxy
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            checks["ollama"] = "ok" if r.status_code == 200 else f"http {r.status_code}"
    except Exception as e:
        checks["ollama"] = f"error: {e}"

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {
        "status":    overall,
        "services":  checks,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── Routers ──────────────────────────────────────────────────────────

app.include_router(auth.router)
app.include_router(memory.router)
app.include_router(hardware.router)
app.include_router(hardware_bridge.router)
app.include_router(knowledge.router)
app.include_router(circuits.router)
app.include_router(websockets.router)
app.include_router(intelligence.router)
app.include_router(push.router)


# ── Arranque directo ─────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)
