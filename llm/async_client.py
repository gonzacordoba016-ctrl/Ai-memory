# llm/async_client.py
#
# Cliente HTTP async centralizado para todas las llamadas al LLM.
# Ventajas:
#   - No bloquea workers de Uvicorn bajo carga concurrente
#   - Reutiliza una única sesión httpx (connection pooling)
#   - Timeout y retry centralizados

import json
import httpx
from typing import Callable, Awaitable, Any
from core.config import get_llm_headers, get_llm_api, get_llm_model
from core.logger import logger

# Shared client with connection pooling — instantiated once at import.
# 120s for firmware generation, connect timeout 10s.
_client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))


async def call_llm_async(
    messages:    list[dict[str, Any]],
    temperature: float = 0.7,
    timeout:     float = 120.0,
    agent_id:    str   = "stratum",
    agent_name:  str   = "Stratum",
    tools:       list[dict[str, Any]] | None = None,
    model:       str   = None,
) -> dict[str, Any]:
    """
    Async LLM call. Returns the full response dict.
    Raises httpx.HTTPError on HTTP failure.
    """
    payload: dict[str, Any] = {
        "model":       model or get_llm_model(),
        "messages":    messages,
        "temperature": temperature,
    }
    if tools:
        payload["tools"]       = tools
        payload["tool_choice"] = "auto"

    response = await _client.post(
        get_llm_api(),
        headers=get_llm_headers(agent_id, agent_name),
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


async def call_llm_text(
    messages:    list[dict[str, Any]],
    temperature: float = 0.0,
    timeout:     float = 30.0,
    agent_id:    str   = "stratum",
    agent_name:  str   = "Stratum",
    model:       str   = None,
    use_cache:   bool  = True,
) -> str:
    """
    Convenience wrapper that returns the response text directly.
    Returns "" on error (never raises).
    Semantic cache active when temperature == 0.0 and use_cache == True.
    """
    resolved_model = model or get_llm_model()

    if use_cache and temperature == 0.0:
        try:
            from llm.cache import llm_cache
            cached = llm_cache.get(messages, resolved_model)
            if cached is not None:
                return cached
        except Exception:
            pass

    try:
        data = await call_llm_async(
            messages=messages,
            temperature=temperature,
            timeout=timeout,
            agent_id=agent_id,
            agent_name=agent_name,
            model=resolved_model,
        )
        text = data["choices"][0]["message"].get("content", "").strip()

        if use_cache and temperature == 0.0 and text:
            try:
                from llm.cache import llm_cache
                llm_cache.set(messages, resolved_model, text)
            except Exception:
                pass

        return text
    except Exception as e:
        logger.error(f"[AsyncLLM] Error en call_llm_text ({agent_id}): {e}")
        return ""


async def stream_llm_async(
    messages:    list[dict[str, Any]],
    on_token:    Callable[[str], Awaitable[None]],
    temperature: float = 0.7,
    agent_id:    str   = "stratum",
    agent_name:  str   = "Stratum",
    model:       str   = None,
) -> str:
    """
    Async token-by-token streaming.
    Calls on_token(str) for each received token.
    Returns the full text when done.
    """
    full_text = ""
    try:
        async with _client.stream(
            "POST",
            get_llm_api(),
            headers=get_llm_headers(agent_id, agent_name),
            json={
                "model":       model or get_llm_model(),
                "messages":    messages,
                "temperature": temperature,
                "stream":      True,
            },
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    token = chunk["choices"][0]["delta"].get("content", "")
                    if token:
                        await on_token(token)
                        full_text += token
                except Exception:
                    continue
    except Exception as e:
        logger.error(f"[AsyncLLM] Error en streaming ({agent_id}): {e}")

    return full_text


async def close() -> None:
    """Close the shared client on server shutdown."""
    await _client.aclose()
