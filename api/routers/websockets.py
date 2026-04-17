# api/routers/websockets.py
# WebSocket handlers: chat (con rate limiting), señal y proactivo

import asyncio
import json
import uuid as uuid_lib
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from api.auth import decode_token, get_current_user
from core.config import MULTI_USER
from database.sql_memory import _default as sql_db
from memory.graph_memory import graph_memory
from tools.signal_reader import signal_reader
from core.logger import logger

router = APIRouter(tags=["websockets"])


async def _ws_require_auth(websocket: WebSocket, token: str = "") -> bool:
    """
    Valida el JWT para conexiones WebSocket (token via query param).
    Retorna True si está autorizado. Si no, envía error y cierra.
    Browsers no pueden enviar Authorization: header en WebSocket connections.
    """
    if not MULTI_USER:
        return True
    payload = decode_token(token)
    if not payload:
        await websocket.accept()
        await websocket.send_text(json.dumps({
            "type":    "error",
            "content": "Token de autenticación requerido o inválido. Pasá ?token=<JWT>",
        }))
        await websocket.close(code=4001)
        return False
    return True

# Rate limiting: segundos mínimos entre mensajes por conexión
_WS_RATE_WINDOW = 3.0


@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket, session: str = None, token: str = ""):
    if not await _ws_require_auth(websocket, token):
        return

    import api.app_state as _state
    await websocket.accept()

    if _state.agent is None:
        await websocket.send_text(json.dumps({
            "type":    "error",
            "content": "El agente está inicializándose, intentá en unos segundos.",
        }))
        await websocket.close()
        return

    agent = _state.agent

    # Gestión de sesión
    session_id = session or str(uuid_lib.uuid4())
    history    = sql_db.get_conversation_by_session(session_id, limit=20)
    resumed    = bool(history) and session is not None

    logger.info(f"WebSocket chat conectado | session={session_id} | resumed={resumed}")

    # Mensaje inicial con session_id para que el cliente lo persista
    from api.server import SERVER_START_TS
    await websocket.send_text(json.dumps({
        "type":         "session",
        "session_id":   session_id,
        "resumed":      resumed,
        "server_start": SERVER_START_TS,
    }))

    # Si retomamos sesión, inyectar historial en el agente
    if resumed and hasattr(agent, 'state'):
        for msg in history[-20:]:
            agent.state.add_message(msg["role"], msg["content"])

    last_message_time = 0.0
    processing = False

    try:
        while True:
            data       = await websocket.receive_text()
            payload    = json.loads(data)
            user_input = payload.get("message", "").strip()

            if not user_input:
                continue

            now = asyncio.get_event_loop().time()
            if processing:
                await websocket.send_text(json.dumps({
                    "type":    "error",
                    "content": "Esperá a que termine la respuesta anterior.",
                }))
                continue
            if now - last_message_time < _WS_RATE_WINDOW:
                await websocket.send_text(json.dumps({
                    "type":    "error",
                    "content": f"Esperá {_WS_RATE_WINDOW:.0f}s entre mensajes.",
                }))
                continue

            last_message_time = now
            processing = True

            # Persistir mensaje del usuario en la sesión
            sql_db.store_message("user", user_input, session_id=session_id)
            sql_db.touch_session(session_id)
            # Auto-título: usar primeras palabras del primer mensaje
            _msgs_so_far = sql_db.get_conversation_by_session(session_id, limit=2)
            if len(_msgs_so_far) <= 1:
                _auto_title = user_input[:60].strip()
                if _auto_title:
                    sql_db.update_session_title(session_id, _auto_title)

            async def on_token(token: str):
                await websocket.send_text(json.dumps({"type": "token", "content": token}))

            try:
                response = await asyncio.wait_for(
                    agent.process_input(user_input, on_token=on_token),
                    timeout=120.0
                )
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({
                    "type":    "error",
                    "content": "El agente tardó demasiado. Intentá de nuevo."
                }))
                processing = False
                continue
            finally:
                processing = False

            # Persistir respuesta del agente en la sesión
            if response:
                sql_db.store_message("assistant", response, session_id=session_id)

            await websocket.send_text(json.dumps({
                "type":        "done",
                "content":     response,
                "facts":       sql_db.get_all_facts(),
                "graph":       graph_memory.stats(),
                "agents_used": getattr(agent, '_last_agents_used', []),
            }))

    except WebSocketDisconnect:
        logger.info(f"WebSocket chat desconectado | session={session_id}")
    except Exception as e:
        logger.error(f"Error en WebSocket chat: {e}")
        try:
            await websocket.send_text(json.dumps({"type": "error", "content": str(e)}))
        except Exception:
            pass


@router.websocket("/ws/signal")
async def ws_signal(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket signal conectado")

    queue: asyncio.Queue = asyncio.Queue(maxsize=200)

    def on_data(data: dict):
        try:
            queue.put_nowait(data)
        except asyncio.QueueFull:
            pass

    signal_reader.add_callback(on_data)

    try:
        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=30)
                await websocket.send_text(json.dumps(data))
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        logger.info("WebSocket signal desconectado")
    except Exception as e:
        logger.error(f"Error en WebSocket signal: {e}")
    finally:
        if on_data in signal_reader._callbacks:
            signal_reader._callbacks.remove(on_data)


@router.websocket("/ws/proactive")
async def ws_proactive(websocket: WebSocket):
    import api.app_state as _state
    await websocket.accept()

    if _state.proactive_engine is None:
        await websocket.send_text(json.dumps({
            "type":    "error",
            "content": "Motor proactivo inicializándose, intentá en unos segundos.",
        }))
        await websocket.close()
        return

    proactive_engine = _state.proactive_engine
    logger.info("WebSocket proactivo conectado")

    queue = proactive_engine.subscribe()

    try:
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=30)
                await websocket.send_text(message)
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        logger.info("WebSocket proactivo desconectado")
    except Exception as e:
        logger.error(f"Error en WebSocket proactivo: {e}")
    finally:
        proactive_engine.unsubscribe(queue)


@router.get("/api/proactive/status")
async def proactive_status(_: str = Depends(get_current_user)):
    import api.app_state as _state
    if _state.proactive_engine is None:
        return {
            "running":  False,
            "clients":  0,
            "initializing": True,
            "intervals": {
                "device_check_seconds":   60,
                "inactive_check_seconds": 3600,
                "error_check_seconds":    1800,
                "daily_summary_seconds":  86400,
            }
        }
    return {
        "running":  _state.proactive_engine._running,
        "clients":  _state.proactive_engine.client_count,
        "intervals": {
            "device_check_seconds":   60,
            "inactive_check_seconds": 3600,
            "error_check_seconds":    1800,
            "daily_summary_seconds":  86400,
        }
    }
