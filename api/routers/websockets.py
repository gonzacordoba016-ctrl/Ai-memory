# api/routers/websockets.py
# WebSocket handlers: chat (con rate limiting), señal y proactivo

import asyncio
import json
import time
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


async def _generate_title_async(websocket: WebSocket, session_id: str, user_input: str):
    """Genera el título en background y lo emite como evento separado."""
    try:
        from llm.async_client import call_llm_text
        raw = await asyncio.wait_for(
            call_llm_text(
                messages=[{"role": "user", "content":
                    f"Resume en máximo 5 palabras, en español, el tema de esta consulta. "
                    f"Solo devolvé el título, sin puntuación ni comillas.\n\nConsulta: {user_input[:200]}"}],
                temperature=0,
                timeout=15,
                agent_id="title-gen",
                agent_name="TitleGen",
            ),
            timeout=15,
        )
        title = (raw or "").strip()[:60]
        if not title:
            return
        sql_db.update_session_title(session_id, title)
        await websocket.send_text(json.dumps({
            "type":       "session_title",
            "session_id": session_id,
            "title":      title,
        }))
    except Exception as e:
        logger.warning(f"[TitleGen] falló en background: {e}")


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
    last_facts_seq = None
    last_graph_seq = None

    try:
        while True:
            data       = await websocket.receive_text()
            payload    = json.loads(data)
            user_input = payload.get("message", "").strip()

            if not user_input:
                continue

            now = time.monotonic()
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
            _msg_start_ts = time.monotonic()

            # Persistir mensaje del usuario en la sesión
            sql_db.store_message("user", user_input, session_id=session_id)
            sql_db.touch_session(session_id)
            _msgs_so_far = sql_db.get_conversation_by_session(session_id, limit=2)
            _is_first_msg = len(_msgs_so_far) <= 1

            async def on_token(token: str):
                await websocket.send_text(json.dumps({"type": "token", "content": token}))

            try:
                _task = asyncio.create_task(
                    agent.process_input(user_input, on_token=on_token)
                )
                _elapsed = 0
                _timeout  = 180
                response  = None
                while not _task.done():
                    try:
                        response = await asyncio.wait_for(
                            asyncio.shield(_task), timeout=15.0
                        )
                        break
                    except asyncio.TimeoutError:
                        _elapsed += 15
                        if _elapsed >= _timeout:
                            _task.cancel()
                            await websocket.send_text(json.dumps({
                                "type":    "error",
                                "content": "El agente tardó demasiado. Intentá de nuevo.",
                            }))
                            response = None
                            break
                        # Heartbeat — mantiene Railway nginx vivo
                        await websocket.send_text(json.dumps({
                            "type": "thinking", "content": "…"
                        }))
                if response is None and not _task.done():
                    pass  # ya enviamos error arriba
                elif response is None and _task.done() and not _task.cancelled():
                    response = _task.result()
            except Exception as _proc_err:
                logger.exception(f"Error en process_input: {_proc_err}")
                await websocket.send_text(json.dumps({
                    "type": "error", "content": str(_proc_err)
                }))
                response = None
            finally:
                processing = False

            # Desempacar respuesta (ahora es dict con text + metadata opcional)
            if isinstance(response, dict):
                response_text   = response.get("text", "")
                agents_used_res = response.get("agents_used", [])
                circuit_id      = response.get("circuit_design_id")
                circuit_name    = response.get("circuit_name")
            else:
                response_text   = response or ""
                agents_used_res = getattr(agent, '_last_agents_used', [])
                circuit_id      = None
                circuit_name    = None

            elapsed_ms = int((time.monotonic() - _msg_start_ts) * 1000)

            # Persistir respuesta del agente en la sesión
            if response_text:
                sql_db.store_message("assistant", response_text, session_id=session_id, elapsed_ms=elapsed_ms)

            # Título: fallback inmediato + generación LLM en background
            if _is_first_msg and response_text:
                _fallback_title = user_input[:60].strip()
                sql_db.update_session_title(session_id, _fallback_title)
                asyncio.create_task(_generate_title_async(
                    websocket, session_id, user_input
                ))

            done_payload = {
                "type":        "done",
                "content":     response_text,
                "agents_used": agents_used_res,
                "elapsed_ms":  elapsed_ms,
            }
            # Incluir facts/graph solo si cambiaron en este ciclo (o en la primera respuesta)
            if last_facts_seq != sql_db._facts_seq:
                done_payload["facts"] = sql_db.get_all_facts()
                last_facts_seq = sql_db._facts_seq
            if last_graph_seq != graph_memory._seq:
                done_payload["graph"] = graph_memory.stats()
                last_graph_seq = graph_memory._seq
            if circuit_id:
                done_payload["circuit_design_id"] = circuit_id
                done_payload["circuit_name"]      = circuit_name

            await websocket.send_text(json.dumps(done_payload))

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
