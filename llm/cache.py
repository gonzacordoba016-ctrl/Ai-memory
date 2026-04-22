# llm/cache.py
#
# Cache semántico para call_llm_text().
# Evita llamadas duplicadas a OpenRouter cuando la consulta es muy similar
# a una anterior (cosine similarity >= THRESHOLD).
#
# Solo se activa para llamadas deterministas (temperature == 0.0).
# El cache es en memoria con TTL — se pierde al reiniciar el servidor.
# Diseño intencional: sin persistencia para evitar respuestas stale entre sesiones.

import time
import hashlib
import numpy as np
from typing import Optional
from core.logger import logger

# ── Configuración ─────────────────────────────────────────────────────────────
CACHE_TTL_SECONDS  = 1800   # 30 minutos
SIMILARITY_THRESHOLD = 0.93  # cosine similarity mínima para considerar hit
MAX_CACHE_ENTRIES  = 512    # evita consumo excesivo de memoria


class SemanticCache:
    """
    Cache en memoria indexado por embedding del prompt.
    Busca hits por similaridad cosine sobre vectores MiniLM (384 dims).
    """

    def __init__(self):
        # Lista de (embedding: np.ndarray, response: str, model: str, ts: float)
        self._entries: list[dict] = []

    def _cosine(self, a: np.ndarray, b: np.ndarray) -> float:
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na == 0 or nb == 0:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    def _embed(self, text: str) -> Optional[np.ndarray]:
        try:
            from infrastructure.embeddings import embedding_model
            vec = embedding_model.embed(text)
            return np.array(vec, dtype=np.float32)
        except Exception as e:
            logger.warning(f"[LLMCache] Error al embedar: {e}")
            return None

    def _prompt_key(self, messages: list[dict]) -> str:
        """Texto representativo del prompt: concatena últimos 2 mensajes."""
        parts = [m.get("content", "") for m in messages[-2:]]
        return " | ".join(parts)[:1000]

    def get(self, messages: list[dict], model: str) -> Optional[str]:
        """Retorna respuesta cacheada si hay un hit, o None."""
        key_text = self._prompt_key(messages)
        now = time.time()

        # ── Fast-path: match exacto por hash MD5 del key_text ─────────
        text_hash = hashlib.md5(key_text.encode()).hexdigest()
        for entry in self._entries:
            if entry.get("hash") != text_hash:
                continue
            if entry["model"] != model:
                continue
            if now - entry["ts"] > CACHE_TTL_SECONDS:
                continue
            age = int(now - entry["ts"])
            logger.info(f"[LLMCache] HIT exact hash age={age}s model={model}")
            return entry["response"]

        # ── Slow-path: similaridad cosine sobre embeddings ────────────
        query_vec = self._embed(key_text)
        if query_vec is None:
            return None

        best_score, best_entry = 0.0, None
        for entry in self._entries:
            if entry["model"] != model:
                continue
            if now - entry["ts"] > CACHE_TTL_SECONDS:
                continue
            score = self._cosine(query_vec, entry["vec"])
            if score > best_score:
                best_score, best_entry = score, entry

        if best_score >= SIMILARITY_THRESHOLD and best_entry:
            age = int(now - best_entry["ts"])
            logger.info(f"[LLMCache] HIT similarity={best_score:.3f} age={age}s model={model}")
            return best_entry["response"]

        return None

    def set(self, messages: list[dict], model: str, response: str) -> None:
        """Almacena una respuesta en el cache."""
        key_text = self._prompt_key(messages)
        vec = self._embed(key_text)
        if vec is None:
            return

        # Evitar duplicados exactos (mismo hash de texto)
        text_hash = hashlib.md5(key_text.encode()).hexdigest()
        self._entries = [e for e in self._entries if e.get("hash") != text_hash]

        # Podar entradas expiradas y aplicar límite de tamaño
        now = time.time()
        self._entries = [e for e in self._entries if now - e["ts"] < CACHE_TTL_SECONDS]
        if len(self._entries) >= MAX_CACHE_ENTRIES:
            self._entries = self._entries[-(MAX_CACHE_ENTRIES // 2):]

        self._entries.append({
            "vec":      vec,
            "response": response,
            "model":    model,
            "ts":       now,
            "hash":     text_hash,
        })

    def stats(self) -> dict:
        now = time.time()
        active = [e for e in self._entries if now - e["ts"] < CACHE_TTL_SECONDS]
        return {"entries": len(active), "ttl_seconds": CACHE_TTL_SECONDS, "threshold": SIMILARITY_THRESHOLD}

    def clear(self) -> None:
        self._entries = []
        logger.info("[LLMCache] Cache limpiado manualmente.")


# Instancia global
llm_cache = SemanticCache()
