# memory/vector_memory.py

import math
import time
from collections import OrderedDict
from datetime import datetime, timezone
from infrastructure.vector_store import vector_store
from core.config import MEMORY_DECAY_RATE
from core.logger import logger

# ── Caché LRU con TTL para búsquedas vectoriales ────────────────────
_CACHE_MAX   = 128   # entradas máximas
_CACHE_TTL   = 300   # segundos (5 min)
_search_cache: OrderedDict = OrderedDict()   # key → (timestamp, result)


def _cache_get(key: str):
    if key not in _search_cache:
        return None
    ts, result = _search_cache[key]
    if time.monotonic() - ts > _CACHE_TTL:
        del _search_cache[key]
        return None
    _search_cache.move_to_end(key)
    return result


def _cache_set(key: str, value):
    if key in _search_cache:
        _search_cache.move_to_end(key)
    _search_cache[key] = (time.monotonic(), value)
    if len(_search_cache) > _CACHE_MAX:
        _search_cache.popitem(last=False)


def invalidate_search_cache():
    """Invalida el caché completo (llamar tras guardar nuevas memorias relevantes)."""
    _search_cache.clear()


def store_memory(text: str, metadata: dict = {}) -> bool:
    """
    Guarda una memoria aplicando consolidación primero.
    Retorna True si se guardó, False si fue descartada por redundante.
    """
    skip_consolidation = {"knowledge", "hardware", "session_summary", "fact_update", "consolidated_summary"}
    mem_type = metadata.get("type", "")

    if mem_type not in skip_consolidation:
        try:
            from memory.memory_consolidator import memory_consolidator
            result = memory_consolidator.process_new_memory(text, metadata)

            if result["action"] == "skip":
                logger.debug(f"[Memory] Descartada por redundante: {text[:50]}...")
                return False

            text = result["text"]

        except Exception as e:
            logger.error(f"[Memory] Error en consolidación: {e}")

    enriched = {
        **metadata,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    vector_store.store(text, enriched)
    invalidate_search_cache()
    return True


def search_memory(query: str, top_k: int = 5) -> list[str]:
    """
    Busca memorias aplicando decaimiento temporal sobre el score de Qdrant.
    Devuelve lista de strings para compatibilidad con el resto del sistema.
    Resultados cacheados por 5 min (LRU 128 entradas).
    """
    cache_key = f"sm:{query}:{top_k}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    raw = vector_store.search(query, top_k=top_k * 3)
    if not raw:
        return []

    now    = datetime.now(timezone.utc)
    scored: list[tuple[float, str]] = []

    for item in raw:
        text      = item["text"]
        sem_score = item["score"]
        ts_str    = item["metadata"].get("timestamp")

        if ts_str:
            try:
                ts       = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                days_old = max((now - ts).total_seconds() / 86400, 0)
                decay    = math.exp(-MEMORY_DECAY_RATE * days_old)
            except Exception:
                decay = 1.0
        else:
            decay = 1.0

        scored.append((sem_score * decay, text))

    scored.sort(key=lambda x: x[0], reverse=True)

    from itertools import islice
    result = [text for _, text in islice(scored, top_k)]
    _cache_set(cache_key, result)
    return result


def search_in_sources(query: str, source_ids: list[str], top_k: int = 4) -> str:
    """
    Busca en vectores que pertenezcan a las fuentes habilitadas del perfil activo.
    Filtra por source_id en el metadata y devuelve un bloque de contexto formateado.
    Retorna "" si no hay resultados.
    """
    if not source_ids:
        return ""

    cache_key = f"sis:{query}:{','.join(sorted(source_ids))}:{top_k}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    raw = vector_store.search(query, top_k=top_k * 4)
    if not raw:
        return ""

    filtered = [
        r for r in raw
        if r["metadata"].get("source_id") in source_ids
        or r["metadata"].get("type") == "knowledge_source"
        and r["metadata"].get("source_id") in source_ids
    ]

    if not filtered:
        _cache_set(cache_key, "")
        return ""

    lines = [f"[{r['metadata'].get('source', 'fuente')}] {r['text']}" for r in filtered[:top_k]]
    result = "Contexto de fuentes habilitadas:\n" + "\n".join(f"- {l}" for l in lines)
    _cache_set(cache_key, result)
    return result


def search_memory_with_scores(query: str, top_k: int = 5) -> list[dict]:
    """Versión extendida que devuelve scores — usada por el grafo y el consolidador.
    Resultados cacheados por 5 min (LRU 128 entradas).
    """
    cache_key = f"sms:{query}:{top_k}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    raw = vector_store.search(query, top_k=top_k * 3)
    if not raw:
        return []

    now    = datetime.now(timezone.utc)
    scored: list[dict] = []

    for item in raw:
        ts_str = item["metadata"].get("timestamp")
        if ts_str:
            try:
                ts       = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                days_old = max((now - ts).total_seconds() / 86400, 0)
                decay    = math.exp(-MEMORY_DECAY_RATE * days_old)
            except Exception:
                decay = 1.0
        else:
            decay = 1.0

        final_score = item["score"] * decay
        scored.append({
            "text":     item["text"],
            "score":    final_score,
            "metadata": item["metadata"],
        })

    scored.sort(key=lambda x: x["score"], reverse=True)

    from itertools import islice
    result = list(islice(scored, top_k))
    _cache_set(cache_key, result)
    return result