# memory/session_summarizer.py

import requests
from datetime import datetime, timezone
from memory.vector_memory import store_memory
from core.config import LLM_API, LLM_MODEL, PROVIDER
from core.logger import logger
import os

SUMMARY_PROMPT = """Resumí la siguiente conversación en 3-5 oraciones.
Incluí: temas principales, decisiones tomadas, datos importantes del usuario que aparezcan.
Sé conciso y objetivo.

Conversación:
{conversation}

Resumen:"""


def summarize_session(history: list[dict]) -> str | None:
    if len(history) < 4:
        logger.info("Sesión muy corta, no se genera resumen.")
        return None

    try:
        conversation = _format_history(history)
        summary      = _call_llm(conversation)

        if not summary:
            return None

        fecha = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        memory_text = f"[Resumen de sesión - {fecha}]\n{summary}"
        store_memory(memory_text, metadata={"type": "session_summary", "date": fecha})

        logger.info(f"Resumen de sesión guardado ({len(history)} mensajes)")
        return summary

    except Exception as e:
        logger.error(f"Error generando resumen de sesión: {e}")
        return None


def _format_history(history: list[dict]) -> str:
    lines = []
    for msg in history:
        role = "Usuario" if msg["role"] == "user" else "Agente"
        lines.append(f"{role}: {msg['content']}")
    return "\n".join(lines)


def _call_llm(conversation: str) -> str | None:
    headers = {"Content-Type": "application/json"}

    if PROVIDER == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            logger.warning("Sin OPENROUTER_API_KEY, no se puede resumir.")
            return None
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        response = requests.post(
            LLM_API,
            headers=headers,
            json={
                "model":       LLM_MODEL,
                "messages":    [{"role": "user", "content": SUMMARY_PROMPT.format(conversation=conversation)}],
                "temperature": 0.3,
            },
            timeout=60
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"Error en _call_llm del summarizer: {e}")
        return None