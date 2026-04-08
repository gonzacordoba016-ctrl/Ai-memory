# api/app_state.py
# Estado compartido de la aplicación — evita imports circulares entre server.py y routers.
# Todos los singletons que los routers necesitan se inicializan aquí.

import asyncio
from agent.agent_controller import AgentController
from agent.proactive_engine import proactive_engine  # noqa: F401 (importado por routers)

agent = AgentController()

# ── Cola de Jobs para operaciones largas (compile, flash, parse_circuit) ──────
job_queue: asyncio.Queue = asyncio.Queue()
jobs: dict[str, dict] = {}
