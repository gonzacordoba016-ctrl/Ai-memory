# api/routers/hardware_state.py
# WebSocket /ws/hardware-state — reads a serial port, parses STATE:{...} JSON
# lines emitted by the state_firmware_addon, and broadcasts live pin state
# to all subscribed clients (circuit_viewer overlay).

import asyncio
import json
import threading
from collections import defaultdict
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["hardware-state"])

# ──────────────────────────────────────────────────────────────────────────────
# In-memory state store
# ──────────────────────────────────────────────────────────────────────────────

# device_key → {"D13": 1, "A0": 512, ...}
_device_state: Dict[str, dict] = {}
# device_key → set of asyncio.Queue for each connected WS client
_subscribers: Dict[str, Set[asyncio.Queue]] = defaultdict(set)
_state_lock = threading.Lock()


def _device_key(port: str, baud: int) -> str:
    return f"{port}@{baud}"


def _update_state(key: str, pins: dict):
    with _state_lock:
        if key not in _device_state:
            _device_state[key] = {}
        _device_state[key].update(pins)


def _broadcast(key: str, payload: dict):
    msg = json.dumps(payload)
    dead: list[asyncio.Queue] = []
    for q in list(_subscribers.get(key, set())):
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _subscribers[key].discard(q)


# ──────────────────────────────────────────────────────────────────────────────
# Serial reader (runs in a daemon thread per device)
# ──────────────────────────────────────────────────────────────────────────────

_reader_threads: Dict[str, threading.Thread] = {}


def _serial_reader_thread(port: str, baud: int, loop: asyncio.AbstractEventLoop):
    key = _device_key(port, baud)
    logger.info(f"[HardwareState] Serial reader iniciado: {key}")
    try:
        import serial  # pyserial
        ser = serial.Serial(port, baud, timeout=2)
    except Exception as e:
        logger.error(f"[HardwareState] No se pudo abrir {port}: {e}")
        err_payload = {"type": "error", "message": f"No se pudo abrir {port}: {e}"}
        asyncio.run_coroutine_threadsafe(
            _async_broadcast(key, err_payload), loop
        )
        return

    try:
        while key in _reader_threads:
            try:
                raw = ser.readline().decode("utf-8", errors="replace").strip()
            except Exception:
                break
            if not raw.startswith("STATE:"):
                continue
            try:
                pins = json.loads(raw[6:])
                _update_state(key, pins)
                payload = {"type": "state", "device": port, "pins": _device_state[key]}
                asyncio.run_coroutine_threadsafe(
                    _async_broadcast(key, payload), loop
                )
            except json.JSONDecodeError:
                pass
    finally:
        try:
            ser.close()
        except Exception:
            pass
        _reader_threads.pop(key, None)
        logger.info(f"[HardwareState] Serial reader cerrado: {key}")


async def _async_broadcast(key: str, payload: dict):
    _broadcast(key, payload)


def _ensure_reader(port: str, baud: int, loop: asyncio.AbstractEventLoop):
    key = _device_key(port, baud)
    if key not in _reader_threads or not _reader_threads[key].is_alive():
        t = threading.Thread(
            target=_serial_reader_thread,
            args=(port, baud, loop),
            daemon=True,
        )
        _reader_threads[key] = t
        t.start()


# ──────────────────────────────────────────────────────────────────────────────
# REST endpoint — last known state snapshot
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/api/hardware-state")
async def get_hardware_state(port: str = "COM3", baud: int = 9600):
    key = _device_key(port, baud)
    return {
        "device": port,
        "baud":   baud,
        "state":  _device_state.get(key, {}),
        "connected": key in _reader_threads and _reader_threads[key].is_alive(),
    }


@router.get("/api/hardware-state/devices")
async def list_devices():
    """List all serial ports visible to the OS."""
    try:
        import serial.tools.list_ports
        ports = [
            {"port": p.device, "description": p.description}
            for p in serial.tools.list_ports.comports()
        ]
    except ImportError:
        ports = []
    return {"ports": ports}


# ──────────────────────────────────────────────────────────────────────────────
# WebSocket endpoint
# ──────────────────────────────────────────────────────────────────────────────

@router.websocket("/ws/hardware-state")
async def ws_hardware_state(
    websocket: WebSocket,
    port: str = "COM3",
    baud: int = 9600,
):
    """
    Connect to receive live pin state from a physical device.
    Query params: ?port=COM3&baud=115200
    Messages: {"type":"state","device":"COM3","pins":{"D13":1,"A0":512,...}}
    """
    await websocket.accept()
    key = _device_key(port, baud)
    loop = asyncio.get_running_loop()

    # Subscribe this client
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    _subscribers[key].add(q)

    # Start serial reader thread if not already running
    _ensure_reader(port, baud, loop)

    logger.info(f"[HardwareState] WS cliente conectado: {key}")

    # Send last known state immediately so the overlay shows something
    if key in _device_state:
        await websocket.send_text(json.dumps({
            "type":   "state",
            "device": port,
            "pins":   _device_state[key],
        }))

    await websocket.send_text(json.dumps({
        "type":    "connected",
        "device":  port,
        "baud":    baud,
        "message": f"Escuchando {port} @ {baud} baud",
    }))

    try:
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=30)
                await websocket.send_text(msg)
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        logger.info(f"[HardwareState] WS cliente desconectado: {key}")
    except Exception as e:
        logger.error(f"[HardwareState] WS error: {e}")
    finally:
        _subscribers[key].discard(q)
