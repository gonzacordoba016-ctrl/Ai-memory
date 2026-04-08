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

import os
import json
import httpx
from typing import Callable, Awaitable, Any
from core.config import get_llm_headers
from core.logger import logger

def _get_llm_api() -> str:
    """Lee la URL del LLM en runtime para evitar valores cacheados del import."""
    import os
    provider = os.getenv("LLM_PROVIDER", "ollama")
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    urls = {
        "ollama":     ollama_url + "/v1/chat/completions",
        "lmstudio":   os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234") + "/v1/chat/completions",
        "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    }
    return urls.get(provider, urls["ollama"])

def _get_llm_model() -> str:
    """Lee el modelo LLM en runtime."""
    import os
    provider = os.getenv("LLM_PROVIDER", "ollama")
    if provider in ("ollama", "lmstudio"):
        return os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
    return os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")

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
    model:       str   = None,
) -> dict[str, Any]:
    """
    Llamada async al LLM. Retorna el dict completo de la respuesta.
    Lanza httpx.HTTPError en caso de fallo HTTP.
    """
    payload = {
        "model":       model or _get_llm_model(),
        "messages":    messages,
        "temperature": temperature,
    }
    if tools:
        payload["tools"]       = tools
        payload["tool_choice"] = "auto"

    response = await _client.post(
        _get_llm_api(),
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
    Wrapper conveniente que retorna directamente el texto de la respuesta.
    Ideal para clasificadores y extractores que solo necesitan el string.
    Retorna "" en caso de error (nunca lanza excepción).

    Semantic cache activo cuando temperature == 0.0 y use_cache == True.
    """
    resolved_model = model or _get_llm_model()

    # ── Semantic cache (solo para llamadas deterministas) ─────────────────
    if use_cache and temperature == 0.0:
        try:
            from llm.cache import llm_cache
            cached = llm_cache.get(messages, resolved_model)
            if cached is not None:
                return cached
        except Exception:
            pass  # cache fallo → continuar normalmente

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

        # Guardar en cache si la respuesta es válida
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
    Streaming async token por token.
    Llama a on_token(str) por cada token recibido.
    Retorna el texto completo al finalizar.
    """
    full_text = ""
    try:
        async with _client.stream(
            "POST",
            _get_llm_api(),
            headers=get_llm_headers(agent_id, agent_name),
            json={
                "model":       model or _get_llm_model(),
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