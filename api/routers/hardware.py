# api/routers/hardware.py
# Endpoints de hardware: dispositivos, firmware, circuitos, biblioteca, visión, señal

import asyncio
from fastapi import APIRouter, Request
from fastapi.responses import Response
from core.logger import logger
from api.limiter import limiter

from database.hardware_memory import hardware_memory
from tools.hardware_detector import detect_devices
from tools.signal_reader import signal_reader
from agent.agents.vision_agent import vision_agent

router = APIRouter(prefix="/api/hardware", tags=["hardware"])


# ── Dispositivos ────────────────────────────────────────────────────

@router.get("/devices")
async def get_hardware_devices():
    connected  = detect_devices()
    registered = hardware_memory.get_all_devices()
    conn_names = {d["name"] for d in connected}
    for d in registered:
        d["connected"] = d["name"] in conn_names
        circuit = hardware_memory.get_circuit_context(d["name"])
        d["has_circuit"]  = circuit is not None
        d["project_name"] = circuit["project_name"] if circuit else ""
    return {
        "connected":  connected,
        "registered": registered,
        "stats":      hardware_memory.get_stats(),
    }


@router.get("/firmware/{device_name}")
async def get_device_firmware(device_name: str):
    history = hardware_memory.get_device_history(device_name, limit=10)
    current = hardware_memory.get_current_firmware(device_name)
    return {"device": device_name, "current": current, "history": history}


@router.get("/firmware/{device_name}/diff")
async def get_firmware_diff(device_name: str):
    """Retorna diff entre las últimas 2 versiones del firmware."""
    history = hardware_memory.get_device_history(device_name, limit=2)
    if len(history) < 2:
        return {"device": device_name, "diff": None, "message": "Menos de 2 versiones"}
    import difflib
    old_code = (history[1].get("code") or "").splitlines(keepends=True)
    new_code = (history[0].get("code") or "").splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        old_code, new_code,
        fromfile=f"v_prev ({history[1].get('timestamp','')[:10]})",
        tofile=f"v_current ({history[0].get('timestamp','')[:10]})",
        lineterm=""
    ))
    return {
        "device":   device_name,
        "diff":     "".join(diff),
        "old_task": history[1].get("task", ""),
        "new_task": history[0].get("task", ""),
        "old_ts":   history[1].get("timestamp", ""),
        "new_ts":   history[0].get("timestamp", ""),
    }


@router.get("/stats")
async def get_hardware_stats():
    return {"stats": hardware_memory.get_stats()}


# ── Circuitos de dispositivos ───────────────────────────────────────

@router.get("/circuit/{device_name}")
async def get_circuit(device_name: str):
    circuit = hardware_memory.get_circuit_context(device_name)
    if not circuit:
        return {"device": device_name, "circuit": None}
    history = hardware_memory.get_circuit_history(device_name)
    return {"device": device_name, "circuit": circuit, "history": history}


@router.get("/circuits")
async def get_all_circuits():
    circuits = hardware_memory.get_all_circuits()
    return {"circuits": circuits, "total": len(circuits)}


@router.post("/circuit/{device_name}")
async def save_circuit(device_name: str, request: Request):
    circuit = await request.json()
    success = hardware_memory.save_circuit_context(device_name, circuit)
    return {"status": "ok" if success else "error", "device": device_name}


@router.post("/circuit/{device_name}/note")
async def add_circuit_note(device_name: str, request: Request):
    body    = await request.json()
    success = hardware_memory.update_circuit_note(device_name, body.get("text", ""))
    return {"status": "ok" if success else "error"}


# ── Biblioteca de proyectos ─────────────────────────────────────────

@router.get("/library")
async def get_library(platform: str = None):
    projects = hardware_memory.get_library(platform=platform)
    return {"projects": projects, "total": len(projects)}


@router.get("/library/search")
async def search_library(q: str, platform: str = None):
    results = hardware_memory.search_library(q, platform=platform)
    return {"query": q, "results": results}


# ── Visión (LLaVA) ──────────────────────────────────────────────────

@router.post("/vision/analyze")
@limiter.limit("3/minute")
async def analyze_circuit_image(request: Request):
    body        = await request.json()
    image_b64   = body.get("image", "")
    device_name = body.get("device_name", "")

    if not image_b64:
        return {"success": False, "message": "No se recibió imagen"}

    result = await asyncio.to_thread(vision_agent.analyze_circuit, image_b64, device_name)
    logger.info(
        f"[Vision] Análisis completado | success={result['success']} | "
        f"components={len(result.get('circuit', {}).get('components', []))}"
    )
    return result


@router.get("/vision/status")
async def vision_status():
    import os
    provider = os.getenv("LLM_PROVIDER", "ollama")
    if provider == "openrouter":
        from agent.agents.vision_agent import VISION_MODEL_OPENROUTER
        return {
            "available": True,
            "provider":  "openrouter",
            "model":     VISION_MODEL_OPENROUTER,
        }
    available = await asyncio.to_thread(vision_agent._check_ollama_model)
    return {
        "available":   available,
        "provider":    "ollama",
        "model":       os.getenv("VISION_MODEL", "llava:7b"),
        "install_cmd": "ollama pull llava:7b",
    }


# ── PlatformIO Export ───────────────────────────────────────────────

@router.get("/firmware/{device_name}/platformio.zip")
async def export_platformio(device_name: str):
    """
    Descarga un ZIP con el último firmware del dispositivo como proyecto PlatformIO.
    Abrí la carpeta en VS Code con la extensión PlatformIO instalada.
    """
    from tools.platformio_exporter import export_platformio_zip

    current = hardware_memory.get_current_firmware(device_name)
    if not current or not current.get("code"):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"No hay firmware guardado para '{device_name}'")

    device_info = hardware_memory.get_device_info(device_name) or {}
    fqbn        = device_info.get("fqbn", "")
    task        = current.get("task", "Firmware generado por Stratum")
    code        = current.get("code", "")

    zip_bytes = await asyncio.to_thread(
        export_platformio_zip, device_name, code, task, fqbn
    )

    safe_name = device_name.replace(" ", "_")
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={safe_name}_platformio.zip"},
    )


# ── Señal ────────────────────────────────────────────────────────────

@router.get("/signal")
async def get_signal_data():
    buffer = signal_reader.get_buffer()
    return {
        "running": signal_reader._running,
        "port":    signal_reader._port,
        "samples": len(buffer),
        "data":    buffer[-100:],
    }


@router.post("/signal/start")
async def start_signal(port: str, baudrate: int = 9600):
    signal_reader.start(port, baudrate)
    return {"status": "started", "port": port}


@router.post("/signal/stop")
async def stop_signal():
    signal_reader.stop()
    return {"status": "stopped"}


# ── Wokwi simulate ───────────────────────────────────────────────────

@router.get("/wokwi/{device_name}")
async def get_wokwi_url(device_name: str):
    """Genera un diagram.json de Wokwi para el circuito guardado del dispositivo."""
    try:
        circuit = hardware_memory.get_circuit_context(device_name)
        if not circuit:
            return {"url": "https://wokwi.com/projects/new", "diagram_json": None, "has_circuit": False}

        from tools.wokwi_simulator import generate_wokwi_diagram
        import json
        diagram = generate_wokwi_diagram(circuit)
        diagram_json = json.dumps(diagram, indent=2)

        return {
            "url": "https://wokwi.com/projects/new",
            "diagram_json": diagram_json,
            "has_circuit": True,
            "device": device_name,
        }
    except Exception as e:
        logger.error(f"[Wokwi] Error generando diagrama: {e}")
        return {"url": "https://wokwi.com/projects/new", "diagram_json": None, "has_circuit": False}
