# agent/agents/base_agent.py
#
# Clase base para todos los sub-agentes.
# Cada agente tiene: nombre, system prompt, herramientas habilitadas,
# y su propio loop ReAct acotado.

import asyncio

from core.logger import logger
from agent.agent_runner import run_agent_loop


class BaseAgent:

    name        : str = "base"
    description : str = "Agente base"
    system_prompt: str = "Eres un asistente útil."
    max_steps   : int = 4

    def __init__(self, client_fn, tool_definitions: list, tool_executor):
        self.client_fn       = client_fn
        self.tool_definitions = tool_definitions
        self.tool_executor   = tool_executor

    def run(self, task: str, context: str = "") -> str:
        """
        Ejecuta el agente sobre una tarea específica.
        Retorna la respuesta final como string.

        `run_agent_loop` es async; este método es sync y típicamente se invoca
        desde el orquestador vía `asyncio.to_thread`. Como el thread worker no
        tiene event loop propio, usamos `asyncio.run` para drivear la corutina.
        """
        system = self.system_prompt
        if context:
            system += f"\n\nContexto disponible:\n{context}"

        messages = [
            {"role": "system",  "content": system},
            {"role": "user",    "content": task},
        ]

        logger.info(f"[{self.name}] Iniciando tarea: {task[:60]}...")

        try:
            answer, _ = asyncio.run(run_agent_loop(
                client_fn=self.client_fn,
                messages=messages,
            ))
            logger.info(f"[{self.name}] Tarea completada")
            return answer or f"[{self.name}] Sin respuesta"
        except Exception as e:
            logger.error(f"[{self.name}] Error: {e}")
            return f"Error en {self.name}: {e}"