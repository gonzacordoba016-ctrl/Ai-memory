# api/app_state.py
# Estado compartido de la aplicación — evita imports circulares entre server.py y routers.
# Los singletons pesados (agent, proactive_engine) se inicializan en background
# en startup_event de api/server.py para que uvicorn responda al healthcheck
# antes de que terminen de cargarse.

import asyncio

# Singletons — None hasta que startup_event los inicialice en background.
agent = None
proactive_engine = None

# ── Cola de Jobs para operaciones largas (compile, flash, parse_circuit) ──────
job_queue: asyncio.Queue = asyncio.Queue()
jobs: dict[str, dict] = {}
