# agent/proactive_consolidator.py
# Lógica de consolidación de memorias antiguas.

import asyncio
from datetime import datetime, timedelta
from core.logger import logger

DAILY_SUMMARY_INTERVAL = 86400  # 24h


class ProactiveConsolidator:
    """
    Consolida memorias antiguas automáticamente cada noche.
    Recibe una referencia al método _broadcast del ProactiveBroadcast.
    """

    def __init__(self, broadcast_fn):
        self._broadcast = broadcast_fn
        self._running   = False

    def stop(self):
        self._running = False

    async def start(self):
        """Lanza el loop de consolidación nocturna."""
        self._running = True
        asyncio.create_task(self._loop_nightly_consolidation())

    # ── Loop ─────────────────────────────────────────────────────────────────

    async def _loop_nightly_consolidation(self):
        """
        Consolida memorias antiguas automáticamente cada noche a medianoche.
        Simula el ciclo de sueño descrito en el KB — fusiona y colapsa
        episodios viejos sin intervención del usuario.
        """
        await self._sleep_until_midnight()

        while self._running:
            logger.info("[Proactive] Iniciando consolidación nocturna automática...")
            try:
                await self.consolidate_old_memories_async(days_threshold=7)
            except Exception as e:
                logger.error(f"[Proactive] Error en consolidación nocturna: {e}")

            await asyncio.sleep(DAILY_SUMMARY_INTERVAL)

    # ── Lógica de consolidación ───────────────────────────────────────────────

    async def consolidate_old_memories_async(self, days_threshold: int = 7):
        """Delega en memory_consolidator y notifica el resultado."""
        from memory.memory_consolidator import memory_consolidator
        result = await memory_consolidator.consolidate_old_memories_async(
            days_threshold=days_threshold
        )

        consolidated = result.get("consolidated", 0)
        if consolidated > 0:
            await self._broadcast({
                "type":    "nightly_consolidation",
                "title":   "Consolidación nocturna completada",
                "message": (
                    f"Procesé **{consolidated}** memorias antiguas y las comprimí "
                    f"en un resumen. La memoria está optimizada."
                ),
                "consolidated": consolidated,
            })
            logger.info(f"[Proactive] Consolidación nocturna: {consolidated} memorias procesadas")
        else:
            logger.info("[Proactive] Consolidación nocturna: sin memorias suficientes")

        return result

    async def consolidate_on_exit(self):
        """Consolida al apagar el servidor si hay suficientes memorias."""
        try:
            from memory.memory_consolidator import memory_consolidator
            await memory_consolidator.consolidate_old_memories_async(days_threshold=1)
            logger.info("[Proactive] Consolidación on-exit completada")
        except Exception as e:
            logger.error(f"[Proactive] Error en consolidación on-exit: {e}")

    # ── Helper ────────────────────────────────────────────────────────────────

    async def _sleep_until_midnight(self):
        """Calcula los segundos hasta la próxima medianoche local y duerme."""
        now           = datetime.now()
        midnight      = now.replace(hour=0, minute=0, second=0, microsecond=0)
        next_midnight = midnight + timedelta(days=1)
        seconds_until = (next_midnight - now).total_seconds()
        logger.info(f"[Proactive] Consolidación nocturna programada en {seconds_until/3600:.1f}h")
        await asyncio.sleep(seconds_until)
