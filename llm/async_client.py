# llm/async_client.py
#
# Cliente HTTP async centralizado para todas las llamadas al LLM.
# Reemplaza requests.post() síncrono en agentes y extractores.
#
# Ventajas:
#   - No bloquea workers de Uvicorn bajo carga concurrente
#   - Reutiliza una única sesión httpx (connection pooling)
#   - Timeout y retry centralizados — un solo lugar para cambiar
#   - Compatible con asyncio.to_thread() para código legacy síncrono

import json
import httpx
from typing import Callable, Awaitable, Any
from core.config import LLM_API, LLM_MODEL, get_llm_headers
from core.logger import logger

# Cliente compartido con connection pooling — se instancia una vez al importar
# timeout: 120s para generación de firmware (puede ser lento), 30s para clasificadores
_client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))


async def call_llm_async(
    messages:    list[dict[str, Any]],
    temperature: float = 0.7,
    timeout:     float = 120.0,
    agent_id:    str   = "stratum",
    agent_name:  str   = "Stratum",
    tools:       list[dict[str, Any]] = [],
) -> dict[str, Any]:
    """
    Llamada async al LLM. Retorna el dict completo de la respuesta.
    Lanza httpx.HTTPError en caso de fallo HTTP.
    """
    payload = {
        "model":       LLM_MODEL,
        "messages":    messages,
        "temperature": temperature,
    }
    if tools:
        payload["tools"]       = tools
        payload["tool_choice"] = "auto"

    response = await _client.post(
        LLM_API,
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
) -> str:
    """
    Wrapper conveniente que retorna directamente el texto de la respuesta.
    Ideal para clasificadores y extractores que solo necesitan el string.
    Retorna "" en caso de error (nunca lanza excepción).
    """
    try:
        data = await call_llm_async(
            messages=messages,
            temperature=temperature,
            timeout=timeout,
            agent_id=agent_id,
            agent_name=agent_name,
        )
        return data["choices"][0]["message"].get("content", "").strip()
    except Exception as e:
        logger.error(f"[AsyncLLM] Error en call_llm_text ({agent_id}): {e}")
        return ""


async def stream_llm_async(
    messages:    list[dict[str, Any]],
    on_token:    Callable[[str], Awaitable[None]],
    temperature: float = 0.7,
    agent_id:    str   = "stratum",
    agent_name:  str   = "Stratum",
) -> str:
    """
    Streaming async token por token.
    Llama a on_token(str) por cada token recibido.
    Retorna el texto completo al finalizar.
    """
    full_text = ""
    try:
        async with _client.stream(
            "POST",
            LLM_API,
            headers=get_llm_headers(agent_id, agent_name),
            json={
                "model":       LLM_MODEL,
                "messages":    messages,
                "temperature": temperature,
                "stream":      True,
            },
            timeout=httpx.Timeout(120.0, connect=10.0),
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
    """Cerrar el cliente al apagar el servidor."""
    await _client.aclose()