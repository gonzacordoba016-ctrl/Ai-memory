# api/server.py

from dotenv import load_dotenv
load_dotenv()

from core.config import validate_config
try:
    validate_config()
except EnvironmentError as e:
    print(f"\n❌ ERROR DE CONFIGURACIÓN:\n{e}\n")
    exit(1)

import asyncio
import json
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from agent.agent_controller import AgentController
from agent.proactive_engine import proactive_engine
from agent.agents.vision_agent import vision_agent
from database.sql_memory import _default as sql_db
from database.hardware_memory import hardware_memory
from memory.vector_memory import search_memory
from memory.graph_memory import graph_memory
from tools.signal_reader import signal_reader
from tools.hardware_detector import detect_devices
from knowledge.knowledge_base import index_knowledge_base, search_knowledge, list_indexed_documents
from core.logger import logger

app = FastAPI(title="Stratum — Hardware Memory Engine")

@app.on_event("startup")
async def startup_event():
    """Lanza el motor proactivo al iniciar el servidor."""
    await proactive_engine.start()
    logger.info("[Server] Motor proactivo iniciado.")

@app.on_event("shutdown")
async def shutdown_event():
    """Cierra el cliente httpx async al apagar el servidor."""
    from llm.async_client import close
    await close()
    logger.info("[Server] Cliente async cerrado.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="api/static"), name="static")

agent = AgentController()


# ── FRONTEND ────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse("api/static/index.html")


# ── HEALTH ──────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


# ── PLUGINS ─────────────────────────────────────────────────

@app.get("/api/plugins")
async def get_plugins():
    """Lista todos los plugins cargados."""
    from tools.plugin_loader import plugin_loader
    return {
        "plugins": plugin_loader.get_plugins_info(),
        "total":   len(plugin_loader.get_plugins_info()),
    }


# ── PERFIL DEL USUARIO ──────────────────────────────────────

@app.get("/api/profile")
async def get_user_profile():
    """Retorna el modelo mental inferido del usuario."""
    return {"profile": agent.profiler.get_profile_summary()}


@app.delete("/api/profile")
async def reset_user_profile():
    """Resetea el perfil del usuario."""
    agent.profiler._save_profile(agent.profiler._default_profile())
    agent.profiler._cache = None
    return {"status": "reset"}


# ── MEMORIA ─────────────────────────────────────────────────────────

@app.get("/api/facts")
async def get_facts():
    return {"facts": sql_db.get_all_facts()}


@app.get("/api/history")
async def get_history(limit: int = 50):
    return {"messages": sql_db.get_recent_messages(limit=limit)}


@app.get("/api/search")
async def memory_search(q: str, top_k: int = 5):
    results = search_memory(q, top_k=top_k)
    return {"query": q, "results": results}


@app.get("/api/stats")
async def get_stats():
    facts    = sql_db.get_all_facts()
    messages = sql_db.get_recent_messages(1000)
    g_stats  = graph_memory.stats()
    hw_stats = hardware_memory.get_stats()
    return {
        "facts_count":    len(facts),
        "messages_count": len(messages),
        "graph_nodes":    g_stats["nodes"],
        "graph_edges":    g_stats["edges"],
        "hw_devices":     hw_stats["devices"],
        "hw_flashes":     hw_stats["total_flashes"],
        "hw_circuits":    hw_stats.get("circuits", 0),
        "timestamp":      datetime.now().isoformat(),
    }


# ── GRAFO ───────────────────────────────────────────────────────────

@app.get("/api/graph")
async def get_graph():
    return {
        "relations": graph_memory.get_all_relations(),
        "stats":     graph_memory.stats(),
    }


# ── AGENTES ─────────────────────────────────────────────────────────

@app.get("/api/agents/status")
async def agents_status():
    return {
        "agents": [
            {"name": "ResearchAgent",  "description": "Búsqueda web y knowledge base"},
            {"name": "CodeAgent",      "description": "Ejecución de código Python"},
            {"name": "MemoryAgent",    "description": "Consulta de memoria"},
            {"name": "HardwareAgent",  "description": "Programación de hardware"},
            {"name": "Orchestrator",   "description": "Coordinador central"},
        ]
    }


# ── HARDWARE ────────────────────────────────────────────────────────

@app.get("/api/hardware/devices")
async def get_hardware_devices():
    connected  = detect_devices()
    registered = hardware_memory.get_all_devices()
    conn_names = {d["name"] for d in connected}
    for d in registered:
        d["connected"] = d["name"] in conn_names
        # Agregar si tiene circuito guardado
        circuit = hardware_memory.get_circuit_context(d["name"])
        d["has_circuit"] = circuit is not None
        d["project_name"] = circuit["project_name"] if circuit else ""
    return {
        "connected":  connected,
        "registered": registered,
        "stats":      hardware_memory.get_stats(),
    }


@app.get("/api/hardware/firmware/{device_name}")
async def get_device_firmware(device_name: str):
    history = hardware_memory.get_device_history(device_name, limit=10)
    current = hardware_memory.get_current_firmware(device_name)
    return {"device": device_name, "current": current, "history": history}


@app.get("/api/hardware/stats")
async def get_hardware_stats():
    return {"stats": hardware_memory.get_stats()}


# ── CIRCUITO ────────────────────────────────────────────────────────

@app.get("/api/hardware/circuit/{device_name}")
async def get_circuit(device_name: str):
    """Retorna el contexto del circuito de un dispositivo."""
    circuit = hardware_memory.get_circuit_context(device_name)
    if not circuit:
        return {"device": device_name, "circuit": None}
    history = hardware_memory.get_circuit_history(device_name)
    return {"device": device_name, "circuit": circuit, "history": history}


@app.get("/api/hardware/circuits")
async def get_all_circuits():
    """Lista todos los circuitos registrados."""
    circuits = hardware_memory.get_all_circuits()
    return {"circuits": circuits, "total": len(circuits)}


@app.post("/api/hardware/circuit/{device_name}")
async def save_circuit(device_name: str, request: Request):
    """Guarda o actualiza el contexto del circuito."""
    circuit = await request.json()
    success = hardware_memory.save_circuit_context(device_name, circuit)
    return {"status": "ok" if success else "error", "device": device_name}


@app.post("/api/hardware/circuit/{device_name}/note")
async def add_circuit_note(device_name: str, request: Request):
    """Agrega una nota al circuito."""
    body = await request.json()
    success = hardware_memory.update_circuit_note(device_name, body.get("text", ""))
    return {"status": "ok" if success else "error"}


# ── BIBLIOTECA ──────────────────────────────────────────────────────

@app.get("/api/hardware/library")
async def get_library(platform: str = None):
    """Lista proyectos de la biblioteca."""
    projects = hardware_memory.get_library(platform=platform)
    return {"projects": projects, "total": len(projects)}


@app.get("/api/hardware/library/search")
async def search_library(q: str, platform: str = None):
    """Busca proyectos en la biblioteca."""
    results = hardware_memory.search_library(q, platform=platform)
    return {"query": q, "results": results}


# ── VISIÓN ──────────────────────────────────────────────────

@app.post("/api/hardware/vision/analyze")
async def analyze_circuit_image(request: Request):
    """
    Analiza una imagen de circuito con LLaVA.

    Body JSON:
        {
            "image": "<base64 sin prefijo data:...>",
            "device_name": "Arduino Uno"   (opcional)
        }

    Returns:
        { success, circuit, saved, message }
    """
    body        = await request.json()
    image_b64   = body.get("image", "")
    device_name = body.get("device_name", "")

    if not image_b64:
        return {"success": False, "message": "No se recibió imagen"}

    # Correr en thread para no bloquear el event loop (puede tardar ~10-30s)
    result = await asyncio.to_thread(
        vision_agent.analyze_circuit, image_b64, device_name
    )

    logger.info(
        f"[Vision] Análisis completado | success={result['success']} | "
        f"components={len(result.get('circuit', {}).get('components', []))}"
    )
    return result


@app.get("/api/hardware/vision/status")
async def vision_status():
    """Verifica si el modelo de visión está disponible."""
    available = await asyncio.to_thread(vision_agent._check_vision_model)
    return {
        "available": available,
        "model":     vision_agent.__class__.__module__ and __import__('os').getenv("VISION_MODEL", "llava:7b"),
        "install_cmd": "ollama pull llava:7b",
    }


# ── SEÑAL ───────────────────────────────────────────────────────────

@app.get("/api/hardware/signal")
async def get_signal_data():
    buffer = signal_reader.get_buffer()
    return {
        "running": signal_reader._running,
        "port":    signal_reader._port,
        "samples": len(buffer),
        "data":    buffer[-100:],
    }


@app.post("/api/hardware/signal/start")
async def start_signal(port: str, baudrate: int = 9600):
    signal_reader.start(port, baudrate)
    return {"status": "started", "port": port}


@app.post("/api/hardware/signal/stop")
async def stop_signal():
    signal_reader.stop()
    return {"status": "stopped"}


# ── KNOWLEDGE BASE ───────────────────────────────────────────────────

@app.get("/api/knowledge/documents")
async def get_knowledge_documents():
    docs = list_indexed_documents()
    return {"documents": docs, "total": len(docs)}


@app.post("/api/knowledge/index")
async def trigger_index(force: bool = False):
    result = await asyncio.to_thread(index_knowledge_base, force=force)
    return {"status": "ok", "indexed": result}


@app.get("/api/knowledge/search")
async def knowledge_search(q: str, top_k: int = 5):
    results = search_knowledge(q, top_k=top_k)
    return {"query": q, "results": results}


# ── WEBSOCKET — CHAT ────────────────────────────────────────────────

@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket chat conectado")

    try:
        while True:
            data       = await websocket.receive_text()
            payload    = json.loads(data)
            user_input = payload.get("message", "").strip()

            if not user_input:
                continue

            loop = asyncio.get_event_loop()

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
                continue

            await websocket.send_text(json.dumps({
                "type":        "done",
                "content":     response,
                "facts":       sql_db.get_all_facts(),
                "graph":       graph_memory.stats(),
                "agents_used": getattr(agent, '_last_agents_used', []),
            }))

    except WebSocketDisconnect:
        logger.info("WebSocket chat desconectado")
    except Exception as e:
        logger.error(f"Error en WebSocket chat: {e}")
        try:
            await websocket.send_text(json.dumps({"type": "error", "content": str(e)}))
        except Exception:
            pass


# ── WEBSOCKET — SEÑAL ───────────────────────────────────────────────

@app.websocket("/ws/signal")
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


# ── WEBSOCKET — PROACTIVO ───────────────────────────────────────────

@app.websocket("/ws/proactive")
async def ws_proactive(websocket: WebSocket):
    """
    Canal de notificaciones proactivas.
    El frontend se suscribe aquí y recibe notificaciones autónomas
    sin necesidad de preguntar (dispositivos conectados, inactividad, errores).
    """
    await websocket.accept()
    logger.info("WebSocket proactivo conectado")

    queue = proactive_engine.subscribe()

    try:
        while True:
            try:
                # Esperar notificación con timeout para mantener vivo el WS
                message = await asyncio.wait_for(queue.get(), timeout=30)
                await websocket.send_text(message)
            except asyncio.TimeoutError:
                # Ping para mantener la conexión viva
                await websocket.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        logger.info("WebSocket proactivo desconectado")
    except Exception as e:
        logger.error(f"Error en WebSocket proactivo: {e}")
    finally:
        proactive_engine.unsubscribe(queue)


@app.get("/api/proactive/status")
async def proactive_status():
    """Estado del motor proactivo."""
    return {
        "running":  proactive_engine._running,
        "clients":  len(proactive_engine._clients),
        "intervals": {
            "device_check_seconds":   30,
            "inactive_check_seconds": 3600,
            "error_check_seconds":    1800,
            "daily_summary_seconds":  86400,
        }
    }


# ── ARRANQUE ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)