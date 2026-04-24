# llm/openrouter_client.py

import httpx
from core.config import get_llm_headers, get_llm_api, get_llm_model


def call_llm_sync(messages: list, tools: list | None = None, model: str = None,
                  response_format: dict = None, timeout: int = 120) -> dict:
    """Synchronous LLM call. Used by circuit_agent and other sync callers."""
    payload = {
        "model":       model or get_llm_model(),
        "messages":    messages,
        "temperature": 0.7,
    }
    if tools:
        payload["tools"]       = tools
        payload["tool_choice"] = "auto"
    if response_format:
        payload["response_format"] = response_format

    response = httpx.post(
        get_llm_api(),
        headers=get_llm_headers(agent_id="memory-agent", agent_name="AIMemoryEngine"),
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()
