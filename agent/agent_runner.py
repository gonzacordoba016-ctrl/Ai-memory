# agent/agent_runner.py
#
# Loop ReAct async: Reason → Act → Observe → Reason → ...
# El agente itera hasta tener una respuesta final o alcanzar el límite de pasos.
#
# Cambios respecto a la versión síncrona:
#   - run_agent_loop() → async def
#   - client_fn ahora es una coroutine async (call_llm_async)
#   - execute_tool() se llama en asyncio.to_thread() para no bloquear
#   - Múltiples tool_calls en un paso se ejecutan en paralelo (asyncio.gather)

import json
import asyncio
from typing import Callable, Awaitable, Any
from core.logger import logger
from tools.tool_registry import TOOL_DEFINITIONS, execute_tool

MAX_STEPS = 6


async def run_agent_loop(
    client_fn: Callable[..., Awaitable[dict[str, Any]]],
    messages:  list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """
    Ejecuta el loop ReAct de forma async.

    Args:
        client_fn: coroutine async que llama al LLM → dict response
        messages:  historial de mensajes

    Returns:
        (respuesta_final, messages_actualizados)
    """
    steps = 0

    while steps < MAX_STEPS:
        steps += 1
        logger.info(f"[Agente] Paso {steps}/{MAX_STEPS}")

        response      = await client_fn(messages=messages, tools=TOOL_DEFINITIONS)
        msg           = response["choices"][0]["message"]
        finish_reason = response["choices"][0]["finish_reason"]

        messages.append(msg)

        if finish_reason == "stop" or not msg.get("tool_calls"):
            logger.info("[Agente] Respuesta final obtenida")
            return msg.get("content", ""), messages

        tool_calls = msg["tool_calls"]
        logger.info(f"[Agente] Tools a ejecutar: {[tc['function']['name'] for tc in tool_calls]}")

        # Ejecutar todas las tool_calls del paso en paralelo
        async def _execute(tool_call: dict) -> dict:
            tool_name = tool_call["function"]["name"]
            tool_args = json.loads(tool_call["function"]["arguments"])
            logger.info(f"[Agente] Ejecutando: {tool_name}({tool_args})")

            # execute_tool puede hacer I/O sincrono — lo corremos en thread
            result = await asyncio.to_thread(execute_tool, tool_name, tool_args)
            logger.info(f"[Agente] {tool_name}: {str(result)[:120]}...")

            return {
                "role":         "tool",
                "tool_call_id": tool_call["id"],
                "content":      str(result),
            }

        tool_results = await asyncio.gather(*[_execute(tc) for tc in tool_calls])
        messages.extend(tool_results)

    # Limite de pasos — forzar respuesta final
    logger.warning("[Agente] Limite de pasos alcanzado, forzando respuesta final")
    messages.append({
        "role":    "user",
        "content": "Por favor, da una respuesta final resumida con lo que encontraste.",
    })
    response = await client_fn(messages=messages, tools=[])
    final    = response["choices"][0]["message"].get("content", "No pude completar la tarea.")
    return final, messages