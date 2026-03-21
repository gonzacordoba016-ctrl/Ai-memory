# memory/vector_memory.py

import math
from datetime import datetime, timezone
from infrastructure.vector_store import vector_store
from core.config import MEMORY_DECAY_RATE
from core.logger import logger


def store_memory(text: str, metadata: dict = {}) -> bool:
    """
    Guarda una memoria aplicando consolidación primero.
    Retorna True si se guardó, False si fue descartada por redundante.
    """
    # Tipos que siempre se guardan sin consolidar
    skip_consolidation = {"knowledge", "hardware", "session_summary", "fact_update", "consolidated_summary"}
    mem_type = metadata.get("type", "")

    if mem_type not in skip_consolidation:
        try:
            from memory.memory_consolidator import memory_consolidator
            result = memory_consolidator.process_new_memory(text, metadata)

            if result["action"] == "skip":
                logger.debug(f"[Memory] Descartada por redundante: {text[:50]}...")
                return False

            # Usar el texto posiblemente fusionado
            text = result["text"]

        except Exception as e:
            logger.error(f"[Memory] Error en consolidación: {e}")

    enriched = {
        **metadata,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    vector_store.store(text, enriched)
    return True


def search_memory(query: str, top_k: int = 5) -> list[str]:
    """
    Busca memorias aplicando decaimiento temporal sobre el score de Qdrant.
    Devuelve lista de strings para compatibilidad con el resto del sistema.
    """
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
    return [text for _, text in islice(scored, top_k)]


def search_memory_with_scores(query: str, top_k: int = 5) -> list[dict]:
    """Versión extendida que devuelve scores — usada por el grafo y el consolidador."""
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
    return list(islice(scored, top_k))