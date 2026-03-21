# core/config.py

import os
import logging

logger = logging.getLogger(__name__)

# ==========================
# MODELOS
# ==========================

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
VISION_MODEL = os.getenv("VISION_MODEL", "llava:7b")

# ==========================
# PROVEEDOR LLM
# ==========================

PROVIDER = os.getenv("LLM_PROVIDER", "ollama")

LLM_URLS = {
    "ollama":     os.getenv("OLLAMA_BASE_URL", "http://localhost:11434") + "/v1/chat/completions",
    "lmstudio":   os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234") + "/v1/chat/completions",
    "openrouter": "https://aethermind-agentos-production.up.railway.app/gateway/v1/chat/completions",
    "gemini":     "https://aethermind-agentos-production.up.railway.app/gateway/v1/chat/completions",
}

LLM_API = LLM_URLS.get(PROVIDER, LLM_URLS["ollama"])

if PROVIDER in ("ollama", "lmstudio"):
    LLM_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
elif PROVIDER == "gemini":
    LLM_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
else:
    LLM_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/openai/gpt-4o-mini")

logger.debug(f"LLM_API: {LLM_API}")
logger.debug(f"LLM_MODEL: {LLM_MODEL}")


def get_llm_headers(agent_id: str = "ai-memory-engine", agent_name: str = "AIMemoryEngine") -> dict:
    """Devuelve los headers correctos según el provider configurado."""
    headers = {"Content-Type": "application/json"}

    if PROVIDER in ("openrouter", "gemini"):
        if PROVIDER == "gemini":
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY no configurada")
        else:
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                raise ValueError("OPENROUTER_API_KEY no configurada")

        headers["Authorization"]  = f"Bearer {api_key}"
        headers["X-Client-Token"] = os.getenv("AETHERMIND_TOKEN", "")
        headers["X-Agent-Id"]     = agent_id
        headers["X-Agent-Name"]   = agent_name
        headers["X-Environment"]  = os.getenv("AETHERMIND_ENV", "development")

    elif PROVIDER == "ollama":
        aethermind_token = os.getenv("AETHERMIND_TOKEN")
        if aethermind_token:
            headers["X-Client-Token"] = aethermind_token
            headers["X-Agent-Id"]     = agent_id
            headers["X-Agent-Name"]   = agent_name
            headers["X-Environment"]  = os.getenv("AETHERMIND_ENV", "development")

    return headers


def validate_config():
    errors = []
    if PROVIDER == "openrouter" and not os.getenv("OPENROUTER_API_KEY"):
        errors.append("OPENROUTER_API_KEY no configurada")
    if PROVIDER == "gemini" and not os.getenv("GEMINI_API_KEY"):
        errors.append("GEMINI_API_KEY no configurada")
    if not LLM_MODEL:
        errors.append("LLM_MODEL no configurado")
    if errors:
        raise EnvironmentError(
            "Configuración inválida:\n" + "\n".join(f"  - {e}" for e in errors)
        )


# ==========================
# MEMORIA
# ==========================

VECTOR_DIMENSION  = 384
VECTOR_COLLECTION = "agent_memory"
MAX_HISTORY_MESSAGES = 20
MAX_SHORT_MEMORY     = 10
MEMORY_DECAY_RATE = float(os.getenv("MEMORY_DECAY_RATE", "0.01"))

# ==========================
# BASES DE DATOS
# ==========================

VECTOR_DB_PATH = "./memory_db"
SQL_DB_PATH    = "./database/memory.db"

# ==========================
# DEBUG
# ==========================

DEBUG     = os.getenv("DEBUG", "true").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")