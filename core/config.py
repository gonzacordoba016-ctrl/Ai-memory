# core/config.py

import os
import logging

logger = logging.getLogger(__name__)

# ==========================
# MODELOS
# ==========================

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Modelo de visión para análisis de circuitos (LLaVA via Ollama)
# Instalarlo con: ollama pull llava:7b
VISION_MODEL = os.getenv("VISION_MODEL", "llava:7b")

# ==========================
# PROVEEDOR LLM
# ==========================

PROVIDER = os.getenv("LLM_PROVIDER", "ollama")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

LLM_URLS = {
    "ollama":     OLLAMA_BASE_URL + "/v1/chat/completions",
    "lmstudio":   os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234") + "/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
}

LLM_API   = LLM_URLS.get(PROVIDER, LLM_URLS["ollama"])
LLM_MODEL = (
    os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
    if PROVIDER in ("ollama", "lmstudio")
    else os.getenv("OPENROUTER_MODEL", "openrouter/openai/gpt-4o-mini")
)

# Modelo dual: fast para routing/memoria, smart para generación de código/circuitos
LLM_MODEL_FAST = os.getenv("LLM_MODEL_FAST", LLM_MODEL)
LLM_MODEL_SMART = os.getenv("LLM_MODEL_SMART", LLM_MODEL)

logger.debug(f"LLM_API: {LLM_API}")
logger.debug(f"LLM_MODEL: {LLM_MODEL}")


def get_llm_headers(agent_id: str = None, agent_name: str = "antigravity") -> dict:
    """Devuelve los headers correctos según el provider configurado.
    Se evalúa en runtime para leer el .env correctamente.
    """
    headers = {"Content-Type": "application/json"}

    # Leer provider en runtime (no al importar el módulo)
    provider = os.getenv("LLM_PROVIDER", "ollama")

    if provider == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("AETHERMIND_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY no configurada")
        # Diagnóstico: loguear el inicio de la key para verificar cuál se está usando
        logger.info(f"[Config] LLM -> openrouter | key prefix: {api_key[:12]}...")
        headers["Authorization"]        = f"Bearer {api_key}"
        headers["HTTP-Referer"]         = "https://stratum.local"
        headers["X-Title"]              = "Stratum AI Memory Engine"

    elif provider == "ollama":
        aethermind_token = os.getenv("AETHERMIND_TOKEN")
        if aethermind_token:
            env_agent_id   = os.getenv("AETHERMIND_AGENT_ID")
            final_agent_id = env_agent_id or agent_id or "ai-memory-engine"
            headers["X-Client-Token"] = aethermind_token
            headers["X-Agent-Id"]     = final_agent_id
            headers["X-Agent-Name"]   = agent_name
            headers["X-Environment"]  = os.getenv("AETHERMIND_ENV", "development")

    return headers


def validate_config():
    """Valida variables críticas al arrancar. Falla rápido con mensaje claro."""
    errors = []
    if PROVIDER == "openrouter" and not os.getenv("OPENROUTER_API_KEY"):
        errors.append("OPENROUTER_API_KEY no configurada")
    if not LLM_MODEL:
        errors.append("OLLAMA_MODEL / OPENROUTER_MODEL no configurado")
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

VECTOR_DB_PATH = os.getenv("VECTOR_DB_PATH", "./memory_db")
SQL_DB_PATH    = os.getenv("MEMORY_DB_PATH", "./database/memory.db")

# Qdrant: si QDRANT_URL está definido se usa server mode, si no path local
QDRANT_URL = os.getenv("QDRANT_URL", "")

# ==========================
# MULTI-USUARIO / AUTH
# ==========================

# MULTI_USER=false → modo single-user, sin autenticación (user_id="default")
# MULTI_USER=true  → JWT requerido en todos los endpoints protegidos
MULTI_USER = os.getenv("MULTI_USER", "false").lower() == "true"

# Clave secreta para firmar tokens JWT. Cambiar en producción.
JWT_SECRET    = os.getenv("JWT_SECRET", "stratum-dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))  # 24h por defecto

# ==========================
# SERVIDOR / PRODUCCIÓN
# ==========================

# Puerto: Railway inyecta PORT; localmente usa 8000
PORT = int(os.getenv("PORT", "8000"))

# CORS: lista de orígenes permitidos separados por coma.
# En producción incluir el dominio de la app y capacitor://localhost para mobile.
_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS: list[str] = (
    ["*"] if _raw_origins.strip() == "*"
    else [o.strip() for o in _raw_origins.split(",") if o.strip()]
)

# ==========================
# DEBUG
# ==========================

DEBUG     = os.getenv("DEBUG", "true").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")