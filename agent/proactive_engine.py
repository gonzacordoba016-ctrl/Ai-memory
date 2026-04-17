# agent/proactive_engine.py
#
# Orquestador del motor proactivo de Stratum.
# Importa ProactiveBroadcast, ProactiveScheduler y ProactiveConsolidator
# y expone la misma interfaz pública que tenía la clase original.
#
# Tipos de notificaciones:
#   - "device_inactive"   → dispositivo sin actividad por N días
#   - "device_connected"  → nuevo dispositivo detectado en el puerto
#   - "recurring_error"   → mismo dispositivo con 2+ fallos recientes
#   - "daily_summary"     → resumen diario de actividad de hardware

import asyncio
from core.logger import logger
from tools.hardware_detector import detect_devices

from agent.proactive_broadcast    import ProactiveBroadcast
from agent.proactive_scheduler    import ProactiveScheduler
from agent.proactive_consolidator import ProactiveConsolidator


class ProactiveEngine:
    """
    Motor de notificaciones proactivas.
    Se instancia una vez en server.py y se lanza con .start().
    """

    def __init__(self):
        self._broadcaster   = ProactiveBroadcast()
        self._scheduler     = ProactiveScheduler(self._broadcaster._broadcast)
        self._consolidator  = ProactiveConsolidator(self._broadcaster._broadcast)
        self._running       = False

    # ── API pública ───────────────────────────────────────────────────────────

    def subscribe(self) -> asyncio.Queue:
        return self._broadcaster.subscribe()

    def unsubscribe(self, q: asyncio.Queue):
        self._broadcaster.unsubscribe(q)

    async def broadcast(self, message: str):
        """Envía un string JSON ya serializado a todos los clientes."""
        await self._broadcaster.broadcast(message)

    async def start(self):
        """Lanza todos los loops de chequeo en background."""
        if self._running:
            return
        self._running = True

        # Cargar estado inicial de puertos conocidos (sin notificar)
        try:
            devices      = await asyncio.to_thread(detect_devices)
            known_ports  = {d["port"] for d in devices if d.get("port")}
        except Exception:
            known_ports  = set()

        logger.info("[Proactive] Motor proactivo iniciado.")

        await self._scheduler.start(known_ports)
        await self._consolidator.start()

    def stop(self):
        self._running = False
        self._scheduler.stop()
        self._consolidator.stop()

    # ── Acceso al estado de clientes (usado por /api/proactive/status) ────────

    @property
    def client_count(self) -> int:
        return self._broadcaster.client_count


def get_proactive_engine() -> "ProactiveEngine":
    """Retorna la instancia global del motor proactivo."""
    return proactive_engine


# Instancia global — importada por server.py
proactive_engine = ProactiveEngine()
