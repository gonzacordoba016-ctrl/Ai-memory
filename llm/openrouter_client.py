# llm/openrouter_client.py

import os
import json
import asyncio
import requests
from core.logger import logger
from core.config import get_llm_headers
from llm.async_client import stream_llm_async, _get_llm_api, _get_llm_model
from agent.agent_runner import run_agent_loop
from tools.tool_registry import TOOL_DEFINITIONS


def _call_llm(messages: list, tools: list = [], model: str = None,
              response_format: dict = None, timeout: int = 120) -> dict:
    """Llamada estándar síncrona al LLM. Usada internamente como fallback."""
    payload = {
        "model":       model or _get_llm_model(),
        "messages":    messages,
        "temperature": 0.7,
    }
    if tools:
        payload["tools"]       = tools
        payload["tool_choice"] = "auto"
    if response_format:
        payload["response_format"] = response_format

    response = requests.post(
        _get_llm_api(),
        headers=get_llm_headers(agent_id="memory-agent", agent_name="AIMemoryEngine"),
        json=payload,
        timeout=timeout
    )
    response.raise_for_status()
    return response.json()


async def _call_llm_async(messages: list, tools: list = []) -> dict:
    """Versión async de _call_llm — usada por run_agent_loop async."""
    from llm.async_client import call_llm_async
    return await call_llm_async(
        messages=messages,
        tools=tools,
        temperature=0.7,
        agent_id="memory-agent",
        agent_name="AIMemoryEngine",
    )


def _stream_final_response(messages: list, on_token) -> str:
    """
    Streaming token por token usando el cliente httpx async centralizado.
    Compatible con on_token síncrono (desde main.py CLI) y async (desde WebSocket).
    """
    async def _run():
        async def _on_token_async(token: str):
            if asyncio.iscoroutinefunction(on_token):
                await on_token(token)
            else:
                on_token(token)

        return await stream_llm_async(
            messages   = messages,
            on_token   = _on_token_async,
            agent_id   = "memory-agent",
            agent_name = "AIMemoryEngine",
        )

    # Reutilizar loop si ya existe (FastAPI), crear uno si es CLI
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        future = asyncio.run_coroutine_threadsafe(_run(), loop)
        return future.result(timeout=120)
    except RuntimeError:
        return asyncio.run(_run())


def generate_response(prompt: str, on_token=None) -> str:
    async def _run():
        messages = [{"role": "user", "content": prompt}]

        final_answer, updated_messages = await run_agent_loop(
            client_fn=_call_llm_async,
            messages=messages
        )

        if not on_token:
            return final_answer or "No pude generar una respuesta."

        stream_messages = [
            m for m in updated_messages
            if m.get("role") != "assistant" or m.get("tool_calls")
        ]
        stream_messages.append({
            "role":    "user",
            "content": "Redacta tu respuesta final de forma clara."
        })
        streamed = await stream_llm_async(
            messages   = stream_messages,
            on_token   = on_token if asyncio.iscoroutinefunction(on_token) else _wrap_sync_token(on_token),
            agent_id   = "memory-agent",
            agent_name = "AIMemoryEngine",
        )
        return streamed or final_answer

    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        return asyncio.run_coroutine_threadsafe(_run(), loop).result(timeout=120)
    except RuntimeError:
        return asyncio.run(_run())


def _wrap_sync_token(on_token):
    """Envuelve un on_token síncrono en una coroutine async."""
    async def _async_token(token: str):
        on_token(token)
    return _async_token