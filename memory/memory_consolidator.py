# memory/memory_consolidator.py
#
# Self-improving memory: detecta contradicciones, redundancias y
# actualiza el estado de la memoria automáticamente.
#
# Tres operaciones:
#   - CONTRADICCIÓN: "trabajo en Acme" vs "trabajo en Google" → actualizar
#   - REDUNDANCIA:   dos episodios casi idénticos → fusionar en uno
#   - OBSOLESCENCIA: hechos que el usuario explícitamente corrigió → marcar

import json
import asyncio
from datetime import datetime, timezone
from core.logger import logger
from llm.async_client import call_llm_text
from memory.vector_memory import search_memory_with_scores, store_memory
from database.sql_memory import _default as sql_db
from memory.graph_memory import graph_memory
from infrastructure.vector_store import vector_store

SIMILARITY_THRESHOLD = 0.88  # score mínimo para considerar redundancia
CONTRADICTION_PROMPT = """Analizá estos dos fragmentos de memoria y determiná si hay contradicción.

Memoria antigua: "{old}"
Memoria nueva:   "{new}"

Respondé ÚNICAMENTE con un JSON:
{{
  "contradiction": true/false,
  "reason": "explicación breve",
  "keep": "old|new|both",
  "merged": "texto fusionado si keep=both, sino null"
}}

Ejemplos de contradicción: trabajo diferente, edad diferente, ciudad diferente.
Ejemplos de NO contradicción: temas distintos, información complementaria."""


class MemoryConsolidator:

    def __init__(self):
        self.contradiction_count = 0
        self.redundancy_count    = 0
        self.merge_count         = 0

    # ======================
    # PUNTO DE ENTRADA
    # ======================

    def process_new_memory(self, new_text: str, metadata: dict = {}) -> dict:
        """
        Antes de guardar una memoria nueva, verificar si contradice
        o es redundante con memorias existentes.
        """
        similar = search_memory_with_scores(new_text, top_k=5)

        if not similar:
            return {"action": "store", "reason": "sin memorias similares", "text": new_text}

        high_sim = [m for m in similar if m["score"] > SIMILARITY_THRESHOLD]

        if not high_sim:
            return {"action": "store", "reason": "sin redundancias detectadas", "text": new_text}

        most_similar = high_sim[0]
        result = _run_async(self._analyze_contradiction(most_similar["text"], new_text))

        if not result:
            return {"action": "store", "reason": "error en análisis", "text": new_text}

        if result.get("contradiction"):
            keep = result.get("keep", "new")

            if keep == "new":
                self.contradiction_count += 1
                logger.info(f"[Consolidator] Contradicción detectada → guardando nueva versión")
                return {
                    "action": "update",
                    "reason": result.get("reason", ""),
                    "text":   new_text,
                    "old":    most_similar["text"],
                }
            elif keep == "both":
                merged = result.get("merged") or new_text
                self.merge_count += 1
                logger.info(f"[Consolidator] Memorias fusionadas")
                return {"action": "store", "reason": "fusionadas", "text": merged}
            else:
                self.redundancy_count += 1
                logger.info(f"[Consolidator] Memoria nueva redundante — descartando")
                return {"action": "skip", "reason": result.get("reason", "redundante"), "text": new_text}

        if most_similar["score"] > 0.95:
            self.redundancy_count += 1
            return {"action": "skip", "reason": "redundante", "text": new_text}

        return {"action": "store", "reason": "información complementaria", "text": new_text}

    # ======================
    # CONSOLIDACIÓN DE HECHOS
    # ======================

    def process_new_fact(self, key: str, new_value: str) -> dict:
        """
        Cuando llega un hecho nuevo (SQLite), verificar si contradice
        el valor actual. Si es así, actualizar y registrar el cambio.
        """
        existing_facts = sql_db.get_all_facts()
        old_value      = existing_facts.get(key)

        if not old_value:
            return {"action": "store", "changed": False}

        if old_value.lower().strip() == new_value.lower().strip():
            return {"action": "skip", "changed": False}

        # Valor diferente — registrar el cambio en memoria vectorial
        logger.info(f"[Consolidator] Hecho actualizado: {key}: '{old_value}' → '{new_value}'")

        change_memory = (
            f"Actualización: {key} cambió de '{old_value}' a '{new_value}' "
            f"el {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        )
        store_memory(change_memory, metadata={
            "type":    "fact_update",
            "key":     key,
            "old":     old_value,
            "new":     new_value,
        })

        # Actualizar también en el grafo
        try:
            mapping = {
                "user_name":     "se_llama",
                "user_job":      "trabaja_como",
                "user_company":  "trabaja_en",
                "user_location": "vive_en",
            }
            predicate = mapping.get(key)
            if predicate:
                # Eliminar arista vieja si existe
                old_val_lower = old_value.lower().strip()
                if graph_memory.graph.has_edge("usuario", old_val_lower):
                    graph_memory.graph.remove_edge("usuario", old_val_lower)
                # Agregar nueva
                graph_memory.add_relation("usuario", predicate, new_value.lower(), source="fact_update")
        except Exception as e:
            logger.error(f"[Consolidator] Error actualizando grafo: {e}")

        return {"action": "update", "changed": True, "old": old_value, "new": new_value}

    # ======================
    # CONSOLIDACIÓN PERIÓDICA
    # ======================

    async def consolidate_old_memories_async(self, days_threshold: int = 7, max_process: int = 50) -> dict:
        """
        Versión async de consolidate_old_memories.
        Llamada por el scheduler nocturno en proactive_engine.
        """
        logger.info("[Consolidator] Iniciando consolidación nocturna async...")

        try:
            results = vector_store.client.scroll(
                collection_name=vector_store.collection,
                limit=max_process,
                with_payload=True,
            )

            points    = results[0]
            now       = datetime.now(timezone.utc)
            old_texts = []

            for point in points:
                payload  = point.payload or {}
                ts_str   = payload.get("timestamp")
                mem_type = payload.get("type", "")

                if mem_type in ("knowledge", "hardware", "fact_update", "session_summary", "consolidated_summary"):
                    continue

                if ts_str:
                    try:
                        ts = datetime.fromisoformat(ts_str)
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                        if (now - ts).days >= days_threshold:
                            old_texts.append(payload.get("text", ""))
                    except Exception:
                        pass

            if len(old_texts) < 3:
                logger.info(f"[Consolidator] Solo {len(old_texts)} memorias antiguas — sin consolidar")
                return {"consolidated": 0, "skipped": len(old_texts)}

            summary = await self._summarize_memories(old_texts[:20])
            if summary:
                store_memory(summary, metadata={
                    "type":         "consolidated_summary",
                    "source_count": len(old_texts),
                    "period_days":  days_threshold,
                })
                logger.info(f"[Consolidator] {len(old_texts)} memorias consolidadas")
                return {"consolidated": len(old_texts), "summary": summary}

        except Exception as e:
            logger.error(f"[Consolidator] Error en consolidación nocturna: {e}")

        return {"consolidated": 0, "error": "fallo en consolidación"}

    def consolidate_on_exit(self, days_threshold: int = 7) -> dict:
        """Wrapper síncrono para llamar desde agent_controller.consolidate_on_exit()."""
        return _run_async(self.consolidate_old_memories_async(days_threshold))

    # Mantener el nombre legacy para compatibilidad con agent_controller existente
    def consolidate_old_memories(self, days_threshold: int = 7, max_process: int = 50) -> dict:
        return _run_async(self.consolidate_old_memories_async(days_threshold, max_process))

    def stats(self) -> dict:
        return {
            "contradictions_resolved": self.contradiction_count,
            "redundancies_skipped":    self.redundancy_count,
            "memories_merged":         self.merge_count,
        }

    # ======================
    # PRIVADOS
    # ======================

    async def _analyze_contradiction(self, old_text: str, new_text: str) -> dict | None:
        """Usa el LLM async para detectar contradicciones entre dos memorias."""
        try:
            content = await call_llm_text(
                messages=[{
                    "role":    "user",
                    "content": CONTRADICTION_PROMPT.format(
                        old=old_text[:300],
                        new=new_text[:300],
                    )
                }],
                temperature=0,
                timeout=20,
                agent_id="consolidator",
                agent_name="MemoryConsolidator",
            )
            if not content:
                return None
            content = content.replace("```json", "").replace("```", "").strip()
            return json.loads(content)
        except Exception as e:
            logger.error(f"[Consolidator] Error analizando contradicción: {e}")
            return None

    async def _summarize_memories(self, texts: list[str]) -> str | None:
        """Genera un resumen consolidado de múltiples memorias antiguas (async)."""
        try:
            joined = "\n".join(f"- {t[:100]}" for t in texts if t)
            content = await call_llm_text(
                messages=[
                    {
                        "role":    "system",
                        "content": "Resumí las siguientes memorias en 3-5 oraciones concisas. Preservá los datos importantes. Devolvé solo el resumen."
                    },
                    {
                        "role":    "user",
                        "content": f"Memorias a consolidar:\n{joined}"
                    }
                ],
                temperature=0.3,
                timeout=40,
                agent_id="consolidator",
                agent_name="MemoryConsolidator",
            )
            return content or None
        except Exception as e:
            logger.error(f"[Consolidator] Error generando resumen: {e}")
            return None


def _run_async(coro):
    """
    Ejecuta una coroutine desde código síncrono.
    Reutiliza el event loop si ya existe (en contexto FastAPI),
    o crea uno nuevo si se llama desde CLI/tests.
    """
    try:
        loop = asyncio.get_running_loop()
        # Hay un loop corriendo (FastAPI) — usar run_coroutine_threadsafe
        import concurrent.futures
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=60)
    except RuntimeError:
        # No hay loop — crear uno (CLI, tests)
        return asyncio.run(coro)


# instancia global
memory_consolidator = MemoryConsolidator()