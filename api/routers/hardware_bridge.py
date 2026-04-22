# api/routers/hardware_bridge.py
#
# WebSocket endpoint que actúa como relay entre el backend (Railway/cloud)
# y el Hardware Bridge Client que corre en la PC del usuario con el Arduino.
#
# Flujo:
#   PC bridge client  ←→  /ws/hardware-bridge  ←→  HardwareAgent.run()
#
# El bridge client se autentica con un token (BRIDGE_TOKEN en .env).
# El HardwareAgent llama a send_to_bridge() para enviar jobs y esperar resultados.

import asyncio
import json
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from api.auth import get_current_user
from core.logger import logger

router = APIRouter(tags=["hardware-bridge"])

# Token de autenticación (opcional — si no está configurado, no se verifica)
BRIDGE_TOKEN = os.getenv("BRIDGE_TOKEN", "")

# Estado global del bridge
_bridge_ws: WebSocket | None = None
_bridge_connected_at: str    = ""
_pending: dict[str, asyncio.Future] = {}  # job_id → Future esperando resultado

# Event loop del proceso uvicorn — se inyecta en startup
_loop: asyncio.AbstractEventLoop | None = None


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def is_bridge_connected() -> bool:
    return _bridge_ws is not None


def bridge_status() -> dict:
    return {
        "connected":     is_bridge_connected(),
        "connected_at":  _bridge_connected_at,
        "pending_jobs":  len(_pending),
    }


async def send_to_bridge(job_type: str, payload: dict, timeout: float = 120) -> dict:
    """
    Envía un job al bridge client y espera la respuesta.
    Se llama desde HardwareAgent (puede ser síncrono via call_bridge_sync).
    """
    if not is_bridge_connected():
        return {"success": False, "error": "Bridge no conectado — arrancá el bridge client en tu PC"}

    job_id = str(uuid.uuid4())
    message = {"job_id": job_id, "type": job_type, **payload}

    fut: asyncio.Future = asyncio.get_running_loop().create_future()
    _pending[job_id] = fut

    try:
        await _bridge_ws.send_text(json.dumps(message))
        result = await asyncio.wait_for(fut, timeout=timeout)
        return result
    except asyncio.TimeoutError:
        logger.error(f"[HardwareBridge] Timeout esperando resultado del job {job_id}")
        return {"success": False, "error": f"Timeout ({timeout}s) — el bridge no respondió"}
    except Exception as e:
        logger.error(f"[HardwareBridge] Error enviando job {job_id}: {e}")
        return {"success": False, "error": str(e)}
    finally:
        _pending.pop(job_id, None)


def call_bridge_sync(job_type: str, payload: dict, timeout: float = 120) -> dict:
    """
    Versión síncrona de send_to_bridge para llamar desde threads síncronos
    (ej: HardwareAgent.run() que corre en un thread pool).
    """
    if _loop is None or not _loop.is_running():
        # Sin loop inyectado — fallback a asyncio.run (crea loop efímero)
        return asyncio.run(send_to_bridge(job_type, payload, timeout))
    future = asyncio.run_coroutine_threadsafe(
        send_to_bridge(job_type, payload, timeout), _loop
    )
    try:
        return future.result(timeout=timeout + 5)
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@router.websocket("/ws/hardware-bridge")
async def ws_hardware_bridge(websocket: WebSocket, token: str = ""):
    global _bridge_ws, _bridge_connected_at

    # Autenticación por token (solo si BRIDGE_TOKEN está configurado)
    if BRIDGE_TOKEN and token != BRIDGE_TOKEN:
        await websocket.close(code=4403, reason="Token inválido")
        logger.warning("[HardwareBridge] Intento de conexión con token inválido")
        return

    if _bridge_ws is not None:
        # Solo un bridge a la vez — desconectar el anterior
        logger.warning("[HardwareBridge] Nuevo bridge conectado — reemplazando el anterior")
        try:
            await _bridge_ws.close()
        except Exception:
            pass

    await websocket.accept()
    _bridge_ws = websocket
    _bridge_connected_at = datetime.utcnow().isoformat()
    logger.info("[HardwareBridge] Bridge client conectado")

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                logger.error(f"[HardwareBridge] JSON inválido del bridge: {raw[:100]}")
                continue

            job_id = data.get("job_id")
            if not job_id:
                continue

            fut = _pending.get(job_id)
            if fut and not fut.done():
                fut.set_result(data)
                logger.info(f"[HardwareBridge] Resultado recibido para job {job_id} | success={data.get('success')}")
            else:
                logger.warning(f"[HardwareBridge] Job {job_id} ya no está pendiente (timeout o cancelado)")

    except WebSocketDisconnect:
        logger.info("[HardwareBridge] Bridge client desconectado")
    except Exception as e:
        logger.error(f"[HardwareBridge] Error en WS bridge: {e}")
    finally:
        if _bridge_ws is websocket:
            _bridge_ws = None
            _bridge_connected_at = ""
        # Resolver todos los Futures pendientes con error
        for job_id, fut in list(_pending.items()):
            if not fut.done():
                fut.set_result({"success": False, "error": "Bridge desconectado durante la operación"})
        _pending.clear()


# ── Status endpoint ───────────────────────────────────────────────────────────

@router.get("/api/hardware/bridge/status")
async def get_bridge_status(_: str = Depends(get_current_user)):
    return bridge_status()


@router.post("/api/hardware/bridge/test")
async def test_bridge(_: str = Depends(get_current_user)):
    """Envía un job 'detect' al bridge client y retorna los dispositivos encontrados."""
    if not is_bridge_connected():
        return {"success": False, "error": "Bridge no conectado — arrancá el bridge con: python run.py bridge --url http://localhost:8000"}
    result = await send_to_bridge("detect", {}, timeout=15)
    return result
