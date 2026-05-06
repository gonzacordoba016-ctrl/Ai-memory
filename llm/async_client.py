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


def _get_client() -> httpx.AsyncClient:
    """
    Devuelve el cliente compartido. Si fue cerrado (race en shutdown / hot-reload),
    instancia uno nuevo en lugar de propagar 'TCPTransport closed=True'.
    """
    global _client
    if _client.is_closed:
        logger.warning("[AsyncLLM] httpx client cerrado — re-instanciando")
        _client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))
    return _client


def _reset_client() -> httpx.AsyncClient:
    """
    Fuerza re-creación del cliente compartido. Necesario cuando el AsyncClient
    está marcado como abierto pero su TCPTransport interno quedó muerto
    (event loop reciclado, pool roto). En esos casos `is_closed` es False
    pero cualquier request lanza RuntimeError('...handler is closed').
    """
    global _client
    try:
        # Best-effort close del cliente roto — si ya está corrupto, ignoramos.
        import asyncio
        loop = asyncio.get_event_loop()
        if not _client.is_closed:
            loop.create_task(_client.aclose())
    except Exception:
        pass
    _client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))
    return _client


def _is_transport_closed_error(err: Exception) -> bool:
    """Detecta errores de transport asyncio cerrado pese a is_closed=False."""
    msg = str(err).lower()
    return (
        isinstance(err, RuntimeError)
        and ("handler is closed" in msg or "transport closed" in msg or "closed=true" in msg)
    )


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

    try:
        response = await _get_client().post(
            get_llm_api(),
            headers=get_llm_headers(agent_id, agent_name),
            json=payload,
            timeout=timeout,
        )
    except RuntimeError as e:
        if not _is_transport_closed_error(e):
            raise
        logger.warning(f"[AsyncLLM] TCPTransport cerrado — re-creando cliente y reintentando ({agent_id})")
        response = await _reset_client().post(
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
        async with _get_client().stream(
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
