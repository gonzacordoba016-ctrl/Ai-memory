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
VISION_MODEL = _env("VISION_MODEL", "llava:7b")

# ==========================
# PROVEEDOR LLM
# ==========================

def _env(key: str, default: str = "") -> str:
    """Lee env var y elimina comillas que Railway/shells pueden inyectar."""
    val = os.getenv(key, default)
    return val.strip().strip('"').strip("'")

def _get_provider() -> str:
    return _env("LLM_PROVIDER", "ollama")

def _get_llm_api() -> str:
    p = _get_provider()
    base = _env("OLLAMA_BASE_URL", "http://localhost:11434")
    urls = {
        "ollama":     base + "/v1/chat/completions",
        "lmstudio":   _env("LMSTUDIO_BASE_URL", "http://localhost:1234") + "/v1/chat/completions",
        "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    }
    return urls.get(p, urls["ollama"])

def _get_llm_model() -> str:
    p = _get_provider()
    if p in ("ollama", "lmstudio"):
        return _env("OLLAMA_MODEL", "qwen2.5:3b")
    return _env("OPENROUTER_MODEL", "openai/gpt-4o-mini")

# Public runtime accessors — read env on every call (with quote-stripping).
# Use these instead of the module-level constants when fresh values are needed.
get_llm_api   = _get_llm_api
get_llm_model = _get_llm_model

# Module-level constants (frozen at import time, kept for backward compat)
PROVIDER        = _get_provider()
OLLAMA_BASE_URL = _env("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_API         = _get_llm_api()
LLM_MODEL       = _get_llm_model()

logger.info(f"[Config] PROVIDER={PROVIDER} | LLM_API={LLM_API} | MODEL={LLM_MODEL}")

# Modelo dual: fast para routing/memoria, smart para generación de código/circuitos
LLM_MODEL_FAST  = _env("LLM_MODEL_FAST",  LLM_MODEL)
LLM_MODEL_SMART = _env("LLM_MODEL_SMART", LLM_MODEL)

logger.debug(f"LLM_API: {LLM_API}")
logger.debug(f"LLM_MODEL: {LLM_MODEL}")


def get_llm_headers(agent_id: str = None, agent_name: str = "antigravity") -> dict:
    """Devuelve los headers correctos según el provider configurado.
    Se evalúa en runtime para leer el .env correctamente.
    """
    headers = {"Content-Type": "application/json"}

    # Leer provider en runtime (no al importar el módulo)
    provider = _env("LLM_PROVIDER", "ollama")

    if provider == "openrouter":
        api_key = _env("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY no configurada")
        # Diagnóstico: loguear el inicio de la key para verificar cuál se está usando
        logger.info(f"[Config] LLM -> openrouter | key prefix: {api_key[:12]}...")
        headers["Authorization"]        = f"Bearer {api_key}"
        headers["HTTP-Referer"]         = "https://stratum.local"
        headers["X-Title"]              = "Stratum AI Memory Engine"

    return headers


def validate_config():
    """Valida variables críticas al arrancar. Falla rápido con mensaje claro."""
    errors = []
    if PROVIDER == "openrouter" and not _env("OPENROUTER_API_KEY"):
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

MEMORY_DECAY_RATE = float(_env("MEMORY_DECAY_RATE", "0.01"))

# ==========================
# BASES DE DATOS
# ==========================

VECTOR_DB_PATH = _env("VECTOR_DB_PATH", "./memory_db")
SQL_DB_PATH    = _env("MEMORY_DB_PATH", "./database/memory.db")
GRAPH_DB_PATH  = _env("GRAPH_DB_PATH",  "./database/graph_memory.json")

# Qdrant: si QDRANT_URL está definido se usa server mode, si no path local
QDRANT_URL = _env("QDRANT_URL", "")

# ==========================
# MULTI-USUARIO / AUTH
# ==========================

# MULTI_USER=false → modo single-user, sin autenticación (user_id="default")
# MULTI_USER=true  → JWT requerido en todos los endpoints protegidos
MULTI_USER = _env("MULTI_USER", "false").lower() == "true"

# Clave secreta para firmar tokens JWT. Cambiar en producción.
JWT_SECRET    = _env("JWT_SECRET", "stratum-dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(_env("JWT_EXPIRE_MINUTES", "1440"))  # 24h por defecto

# ==========================
# SERVIDOR / PRODUCCIÓN
# ==========================

# Puerto: Railway inyecta PORT; localmente usa 8000
PORT = int(_env("PORT", "8000"))

# CORS: lista de orígenes permitidos separados por coma.
# Sobreescribir con la variable de entorno ALLOWED_ORIGINS en Railway.
# Default seguro: solo el dominio de producción + localhost para dev.
_CORS_DEFAULT = (
    "http://localhost:3000,"
    "http://localhost:8000,"
    "http://127.0.0.1:8000,"
    "capacitor://localhost"
)
_raw_origins = _env("ALLOWED_ORIGINS", _CORS_DEFAULT)
ALLOWED_ORIGINS: list[str] = (
    ["*"] if _raw_origins.strip() == "*"
    else [o.strip() for o in _raw_origins.split(",") if o.strip()]
)

# ==========================
# DEBUG
# ==========================

DEBUG     = _env("DEBUG", "true").lower() == "true"
LOG_LEVEL = _env("LOG_LEVEL", "DEBUG" if DEBUG else "INFO")