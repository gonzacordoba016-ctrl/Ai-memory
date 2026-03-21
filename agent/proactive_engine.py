# agent/proactive_engine.py
#
# Motor de comportamiento proactivo de Stratum.
# Corre en background y genera notificaciones autónomas sin que el usuario
# tenga que preguntar. Se comunica con el frontend via WebSocket /ws/proactive.
#
# Tipos de notificaciones:
#   - "device_inactive"   → dispositivo sin actividad por N días
#   - "device_connected"  → nuevo dispositivo detectado en el puerto
#   - "recurring_error"   → mismo dispositivo con 2+ fallos recientes
#   - "daily_summary"     → resumen diario de actividad de hardware

import asyncio
import json
from datetime import datetime, timezone, timedelta
from core.logger import logger
from database.hardware_memory import hardware_memory
from tools.hardware_detector import detect_devices


# ── Intervalos de chequeo (en segundos) ──────────────────────────────────────

CHECK_CONNECTED_INTERVAL  = 30     # Detectar nuevos dispositivos USB
CHECK_INACTIVE_INTERVAL   = 3600   # Chequear dispositivos inactivos (1h)
CHECK_ERRORS_INTERVAL     = 1800   # Chequear errores recurrentes (30min)
DAILY_SUMMARY_INTERVAL    = 86400  # Resumen diario (24h)

INACTIVE_THRESHOLD_DAYS   = 3      # Días sin actividad para considerar inactivo


class ProactiveEngine:
    """
    Motor de notificaciones proactivas.
    Se instancia una vez en server.py y se lanza con .start().
    """

    def __init__(self):
        self._clients: set[asyncio.Queue] = set()
        self._known_ports: set[str]       = set()   # Para detectar nuevas conexiones
        self._running                     = False

    # =========================================================================
    # API pública
    # =========================================================================

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

    async def start(self):
        """Lanza todos los loops de chequeo en background."""
        if self._running:
            return
        self._running = True

        # Cargar estado inicial de puertos conocidos (sin notificar)
        try:
            devices = await asyncio.to_thread(detect_devices)
            self._known_ports = {d["port"] for d in devices if d.get("port")}
        except Exception:
            pass

        logger.info("[Proactive] Motor proactivo iniciado.")

        asyncio.create_task(self._loop_check_connected())
        asyncio.create_task(self._loop_check_inactive())
        asyncio.create_task(self._loop_check_errors())
        asyncio.create_task(self._loop_daily_summary())
        asyncio.create_task(self._loop_nightly_consolidation())

    def stop(self):
        self._running = False

    # =========================================================================
    # Loops de chequeo
    # =========================================================================

    async def _loop_check_connected(self):
        """Detecta nuevos dispositivos conectados al USB."""
        while self._running:
            try:
                await self._check_new_devices()
            except Exception as e:
                logger.error(f"[Proactive] Error en check_connected: {e}")
            await asyncio.sleep(CHECK_CONNECTED_INTERVAL)

    async def _loop_check_inactive(self):
        """Notifica sobre dispositivos sin actividad reciente."""
        await asyncio.sleep(60)  # Esperar 1 minuto antes del primer chequeo
        while self._running:
            try:
                await self._check_inactive_devices()
            except Exception as e:
                logger.error(f"[Proactive] Error en check_inactive: {e}")
            await asyncio.sleep(CHECK_INACTIVE_INTERVAL)

    async def _loop_check_errors(self):
        """Detecta patrones de errores recurrentes."""
        await asyncio.sleep(120)  # Esperar 2 minutos antes del primer chequeo
        while self._running:
            try:
                await self._check_recurring_errors()
            except Exception as e:
                logger.error(f"[Proactive] Error en check_errors: {e}")
            await asyncio.sleep(CHECK_ERRORS_INTERVAL)

    async def _loop_daily_summary(self):
        """Emite un resumen diario de actividad."""
        await asyncio.sleep(300)  # 5 minutos después del arranque
        while self._running:
            try:
                await self._emit_daily_summary()
            except Exception as e:
                logger.error(f"[Proactive] Error en daily_summary: {e}")
            await asyncio.sleep(DAILY_SUMMARY_INTERVAL)

    # =========================================================================
    # Lógica de cada chequeo
    # =========================================================================

    async def _check_new_devices(self):
        """Compara puertos actuales con los conocidos y notifica si hay nuevos."""
        devices      = await asyncio.to_thread(detect_devices)
        current_ports = {d["port"] for d in devices if d.get("port")}
        new_ports    = current_ports - self._known_ports

        for port in new_ports:
            device = next((d for d in devices if d.get("port") == port), None)
            if not device:
                continue

            name = device.get("name", "Dispositivo desconocido")
            logger.info(f"[Proactive] Nuevo dispositivo detectado: {name} en {port}")

            # Verificar si tiene historial previo
            history = await asyncio.to_thread(
                hardware_memory.get_device_history, name, 1
            )
            has_history = bool(history)

            msg = (
                f"Detecté que **{name}** se conectó en `{port}`."
            )
            if has_history:
                last = history[0]
                msg += (
                    f"\nÚltimo proyecto: _{last['task'][:60]}_"
                    f" ({last['timestamp'][:10]})."
                    f"\n¿Continuamos con ese proyecto?"
                )
            else:
                msg += "\nEs la primera vez que lo registro. ¿Qué querés programar?"

            await self._broadcast({
                "type":    "device_connected",
                "title":   "Dispositivo conectado",
                "message": msg,
                "device":  name,
                "port":    port,
                "action":  "program" if has_history else "new",
            })

        # Detectar dispositivos desconectados (sin notificar, solo actualizar estado)
        self._known_ports = current_ports

    async def _check_inactive_devices(self):
        """Notifica sobre dispositivos sin actividad en los últimos N días."""
        devices = await asyncio.to_thread(hardware_memory.get_all_devices)
        now     = datetime.now(timezone.utc)

        for device in devices:
            try:
                last_seen_str = device.get("last_seen", "")
                if not last_seen_str:
                    continue

                # Parsear timestamp — SQLite puede devolver distintos formatos
                try:
                    last_seen = datetime.fromisoformat(last_seen_str)
                    if last_seen.tzinfo is None:
                        last_seen = last_seen.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue

                days_inactive = (now - last_seen).days

                if days_inactive >= INACTIVE_THRESHOLD_DAYS:
                    current = await asyncio.to_thread(
                        hardware_memory.get_current_firmware, device["name"]
                    )
                    if not current:
                        continue

                    await self._broadcast({
                        "type":    "device_inactive",
                        "title":   "Proyecto pausado",
                        "message": (
                            f"Hace **{days_inactive} días** no trabajás con "
                            f"**{device['name']}**.\n"
                            f"Último proyecto: _{current['task'][:60]}_.\n"
                            f"¿Querés retomarlo?"
                        ),
                        "device":        device["name"],
                        "days_inactive": days_inactive,
                        "last_task":     current["task"],
                    })

            except Exception as e:
                logger.error(f"[Proactive] Error procesando dispositivo {device.get('name')}: {e}")

    async def _check_recurring_errors(self):
        """Detecta si un dispositivo tuvo 2+ fallos recientes."""
        devices = await asyncio.to_thread(hardware_memory.get_all_devices)

        for device in devices:
            try:
                history = await asyncio.to_thread(
                    hardware_memory.get_device_history, device["name"], 5
                )
                if len(history) < 2:
                    continue

                # Contar fallos en los últimos 5 registros
                recent_failures = [h for h in history if not h.get("success", True)]

                if len(recent_failures) >= 2:
                    failure_notes = [
                        f["notes"][:80] for f in recent_failures if f.get("notes")
                    ]
                    note_summary = (
                        "\nErrores detectados:\n" +
                        "\n".join(f"  • {n}" for n in failure_notes[:2])
                        if failure_notes else ""
                    )

                    await self._broadcast({
                        "type":    "recurring_error",
                        "title":   "Errores recurrentes detectados",
                        "message": (
                            f"**{device['name']}** tuvo **{len(recent_failures)} fallos** "
                            f"en sus últimas {len(history)} sesiones."
                            f"{note_summary}\n"
                            f"¿Querés que analice el problema?"
                        ),
                        "device":          device["name"],
                        "failure_count":   len(recent_failures),
                        "suggested_action": "debug",
                    })

            except Exception as e:
                logger.error(f"[Proactive] Error en check_errors para {device.get('name')}: {e}")

    async def _emit_daily_summary(self):
        """Emite un resumen de actividad del día si hay datos relevantes."""
        try:
            stats   = await asyncio.to_thread(hardware_memory.get_stats)
            devices = await asyncio.to_thread(hardware_memory.get_all_devices)

            if not devices:
                return

            # Solo emitir si hay actividad real (más de 0 flashes)
            if stats.get("total_flashes", 0) == 0:
                return

            device_lines = []
            for d in devices[:5]:  # Máximo 5 dispositivos en el resumen
                current = await asyncio.to_thread(
                    hardware_memory.get_current_firmware, d["name"]
                )
                if current:
                    device_lines.append(
                        f"  • **{d['name']}** — {current['task'][:50]}"
                    )

            summary = (
                f"📊 **Resumen de Stratum**\n"
                f"Dispositivos registrados: {stats.get('devices', 0)}\n"
                f"Flashes totales: {stats.get('total_flashes', 0)}\n"
            )
            if device_lines:
                summary += "Estado actual:\n" + "\n".join(device_lines)

            await self._broadcast({
                "type":    "daily_summary",
                "title":   "Resumen diario",
                "message": summary,
                "stats":   stats,
            })

        except Exception as e:
            logger.error(f"[Proactive] Error en daily_summary: {e}")

    async def _loop_nightly_consolidation(self):
        """
        Consolida memorias antiguas automáticamente cada noche a medianoche.
        Simula el ciclo de sueño descrito en el KB — fusiona y colapsa
        episodios viejos sin intervención del usuario.
        """
        # Esperar hasta la próxima medianoche local antes del primer ciclo
        await self._sleep_until_midnight()

        while self._running:
            logger.info("[Proactive] Iniciando consolidación nocturna automática...")
            try:
                from memory.memory_consolidator import memory_consolidator
                result = await memory_consolidator.consolidate_old_memories_async(days_threshold=7)

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

            except Exception as e:
                logger.error(f"[Proactive] Error en consolidación nocturna: {e}")

            # Esperar 24 horas hasta la próxima medianoche
            await asyncio.sleep(DAILY_SUMMARY_INTERVAL)

    async def _sleep_until_midnight(self):
        """Calcula los segundos hasta la próxima medianoche local y duerme."""
        from datetime import datetime as dt
        now         = dt.now()
        midnight    = now.replace(hour=0, minute=0, second=0, microsecond=0)
        # Si ya pasó medianoche hoy, apuntar a mañana
        from datetime import timedelta
        next_midnight = midnight + timedelta(days=1)
        seconds_until = (next_midnight - now).total_seconds()
        logger.info(f"[Proactive] Consolidación nocturna programada en {seconds_until/3600:.1f}h")
        await asyncio.sleep(seconds_until)

    # =========================================================================
    # Broadcast a todos los clientes conectados
    # =========================================================================

    async def _broadcast(self, payload: dict):
        """Envía una notificación a todos los clientes WebSocket suscriptos."""
        if not self._clients:
            # Guardar en log aunque no haya clientes conectados
            logger.info(f"[Proactive] Notificación (sin clientes): {payload['title']}")
            return

        payload["timestamp"] = datetime.now(timezone.utc).isoformat()
        message              = json.dumps(payload)

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


# Instancia global — importada por server.py
proactive_engine = ProactiveEngine()