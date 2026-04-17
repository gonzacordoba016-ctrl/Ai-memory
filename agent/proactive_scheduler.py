# agent/proactive_scheduler.py
# Loops de chequeo periódico y triggers de tiempo.

import asyncio
from datetime import datetime, timezone
from core.logger import logger
from database.hardware_memory import hardware_memory
from tools.hardware_detector import detect_devices

async def _push(title: str, body: str):
    try:
        from tools.push_notifier import send_push_to_all
        await asyncio.to_thread(send_push_to_all, title, body)
    except Exception:
        pass

# ── Intervalos de chequeo (en segundos) ──────────────────────────────────────
CHECK_CONNECTED_INTERVAL  = 60     # Detectar nuevos dispositivos USB
CHECK_INACTIVE_INTERVAL   = 3600   # Chequear dispositivos inactivos (1h)
CHECK_ERRORS_INTERVAL     = 1800   # Chequear errores recurrentes (30min)
DAILY_SUMMARY_INTERVAL    = 86400  # Resumen diario (24h)

INACTIVE_THRESHOLD_DAYS   = 3      # Días sin actividad para considerar inactivo


class ProactiveScheduler:
    """
    Loops periódicos de chequeo de hardware.
    Recibe una referencia al método _broadcast del ProactiveBroadcast.
    """

    def __init__(self, broadcast_fn):
        self._broadcast      = broadcast_fn
        self._running        = False
        self._known_ports: set[str] = set()

    def stop(self):
        self._running = False

    async def start(self, known_ports: set[str]):
        """Inicia todos los loops. known_ports es el estado inicial de puertos."""
        self._running     = True
        self._known_ports = known_ports

        asyncio.create_task(self._loop_check_connected())
        asyncio.create_task(self._loop_check_inactive())
        asyncio.create_task(self._loop_check_errors())
        asyncio.create_task(self._loop_daily_summary())

    # ── Loops ────────────────────────────────────────────────────────────────

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
        await asyncio.sleep(60)
        while self._running:
            try:
                await self._check_inactive_devices()
            except Exception as e:
                logger.error(f"[Proactive] Error en check_inactive: {e}")
            await asyncio.sleep(CHECK_INACTIVE_INTERVAL)

    async def _loop_check_errors(self):
        """Detecta patrones de errores recurrentes."""
        await asyncio.sleep(120)
        while self._running:
            try:
                await self._check_recurring_errors()
            except Exception as e:
                logger.error(f"[Proactive] Error en check_errors: {e}")
            await asyncio.sleep(CHECK_ERRORS_INTERVAL)

    async def _loop_daily_summary(self):
        """Emite un resumen diario de actividad."""
        await asyncio.sleep(300)
        while self._running:
            try:
                await self._emit_daily_summary()
            except Exception as e:
                logger.error(f"[Proactive] Error en daily_summary: {e}")
            await asyncio.sleep(DAILY_SUMMARY_INTERVAL)

    # ── Lógica de cada chequeo ────────────────────────────────────────────────

    async def _check_new_devices(self):
        """Compara puertos actuales con los conocidos y notifica si hay nuevos."""
        devices       = await asyncio.to_thread(detect_devices)
        current_ports = {d["port"] for d in devices if d.get("port")}
        new_ports     = current_ports - self._known_ports

        for port in new_ports:
            device = next((d for d in devices if d.get("port") == port), None)
            if not device:
                continue

            name = device.get("name", "Dispositivo desconocido")
            logger.info(f"[Proactive] Nuevo dispositivo detectado: {name} en {port}")

            history     = await asyncio.to_thread(hardware_memory.get_device_history, name, 1)
            has_history = bool(history)

            msg = f"Detecté que **{name}** se conectó en `{port}`."
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
            await _push("Dispositivo conectado", f"{name} en {port}")

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
                    await _push("Proyecto pausado", f"{device['name']} inactivo {days_inactive} días")

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
                        "device":           device["name"],
                        "failure_count":    len(recent_failures),
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
            if stats.get("total_flashes", 0) == 0:
                return

            device_lines = []
            for d in devices[:5]:
                current = await asyncio.to_thread(
                    hardware_memory.get_current_firmware, d["name"]
                )
                if current:
                    device_lines.append(f"  • **{d['name']}** — {current['task'][:50]}")

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
