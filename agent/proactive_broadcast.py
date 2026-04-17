# agent/proactive_broadcast.py
# Broadcast WebSocket a clientes conectados.

import asyncio
import json
from datetime import datetime, timezone
from core.logger import logger


class ProactiveBroadcast:
    """Gestiona la lista de clientes WebSocket y el envío de notificaciones."""

    def __init__(self):
        self._clients: set[asyncio.Queue] = set()

    # ── API pública ──────────────────────────────────────────────────────────

    def subscribe(self) -> asyncio.Queue:
        """Registra un nuevo cliente WebSocket y retorna su queue."""
        q = asyncio.Queue(maxsize=50)
        self._clients.add(q)
        logger.info(f"[Proactive] Cliente suscripto. Total: {len(self._clients)}")
        return q

    def unsubscribe(self, q: asyncio.Queue):
        """Elimina un cliente WebSocket."""
        self._clients.discard(q)
        logger.info(f"[Proactive] Cliente desuscripto. Total: {len(self._clients)}")

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def broadcast(self, message: str):
        """Envía un string JSON ya serializado a todos los clientes."""
        if not self._clients:
            return
        dead_clients = set()
        for q in self._clients:
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                dead_clients.add(q)
        for q in dead_clients:
            self._clients.discard(q)

    async def _broadcast(self, payload: dict):
        """Envía una notificación a todos los clientes WebSocket y push (si hay tokens)."""
        payload["timestamp"] = datetime.now(timezone.utc).isoformat()

        # Push notification a dispositivos móviles registrados
        try:
            from tools.push_notifier import send_push_to_all
            asyncio.create_task(send_push_to_all(
                title = payload.get("title", "Stratum"),
                body  = payload.get("message", ""),
                data  = {"type": payload.get("type", "")},
            ))
        except Exception:
            pass

        if not self._clients:
            logger.info(f"[Proactive] Notificación (sin clientes WS): {payload['title']}")
            return

        message = json.dumps(payload)

        dead_clients = set()
        for q in self._clients:
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                dead_clients.add(q)

        for q in dead_clients:
            self._clients.discard(q)

        logger.info(
            f"[Proactive] Notificación enviada a {len(self._clients)} clientes: "
            f"{payload['title']}"
        )
