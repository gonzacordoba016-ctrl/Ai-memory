# api/routers/circuits.py
# Circuit Router: parseo de circuitos, esquemáticos SVG, breadboard 3D, PCB, Gerber, firmware

import asyncio
import uuid as uuid_lib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response
from api.auth import get_current_user
from api.limiter import limiter
from pydantic import BaseModel

from agent.agents.circuit_agent import CircuitAgent
from database.hardware_memory import hardware_memory
from tools.schematic_renderer import SchematicRenderer
from tools.breadboard_renderer import BreadboardRenderer
from tools.pcb_renderer import PCBRenderer
from tools.firmware_generator import generate_firmware
from core.logger import logger

router = APIRouter(prefix="/api/circuits", tags=["circuits"], dependencies=[Depends(get_current_user)])

# Singleton para CircuitAgent — una sola instancia + conexión SQLite por proceso
_circuit_agent: CircuitAgent = None


def _get_circuit_agent() -> CircuitAgent:
    global _circuit_agent
    if _circuit_agent is None:
        _circuit_agent = CircuitAgent()
    return _circuit_agent


class FirmwareRequest(BaseModel):
    device_name: str
    task_description: str = "Generar firmware basado en el circuito guardado"


@router.get("/viewer", response_class=HTMLResponse)
async def get_circuit_viewer():
    with open("api/static/circuit_viewer.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@router.post("/parse")
@limiter.limit("5/minute")
async def parse_circuit(request: Request, description: str, mcu: str = "Arduino Uno"):
    agent  = _get_circuit_agent()
    result = await asyncio.to_thread(agent.parse_circuit, description, mcu)
    if result:
        return JSONResponse(content=result)
    return JSONResponse(content={"error": "No se pudo parsear el circuito"}, status_code=400)


@router.get("/{circuit_id}/schematic.svg")
async def get_schematic_svg(circuit_id: int):
    agent        = _get_circuit_agent()
    circuit_data = agent.get_circuit_by_id(circuit_id)
    if not circuit_data:
        return JSONResponse(content={"error": "Circuito no encontrado"}, status_code=404)
    svg = SchematicRenderer().render_schematic_svg(circuit_data)
    return HTMLResponse(content=svg, media_type="image/svg+xml")


@router.get("/{circuit_id}/report.pdf")
async def get_circuit_report_pdf(
    circuit_id: int,
    include_firmware:  bool = Query(default=True),
    include_decisions: bool = Query(default=True),
):
    """Genera y descarga un reporte PDF del proyecto de ingeniería."""
    try:
        from tools.pdf_exporter import generate_project_pdf
        pdf_bytes = generate_project_pdf(
            circuit_id=circuit_id,
            include_firmware=include_firmware,
            include_decisions=include_decisions,
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=stratum_circuit_{circuit_id}.pdf"},
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando PDF: {e}")


@router.get("/{circuit_id}/breadboard")
async def get_breadboard_3d(circuit_id: int):
    agent        = _get_circuit_agent()
    circuit_data = agent.get_circuit_by_id(circuit_id)
    if not circuit_data:
        return JSONResponse(content={"error": "Circuito no encontrado"}, status_code=404)
    scene = BreadboardRenderer().render_breadboard_3d(circuit_data)
    return JSONResponse(content=scene)


@router.get("/{circuit_id}/pcb.svg")
async def get_pcb_svg(circuit_id: int):
    agent        = _get_circuit_agent()
    circuit_data = agent.get_circuit_by_id(circuit_id)
    if not circuit_data:
        return JSONResponse(content={"error": "Circuito no encontrado"}, status_code=404)
    svg = PCBRenderer().render_pcb_svg(circuit_data)
    return HTMLResponse(content=svg, media_type="image/svg+xml")


@router.get("/{circuit_id}/gerber")
async def get_gerber_files(circuit_id: int):
    agent        = _get_circuit_agent()
    circuit_data = agent.get_circuit_by_id(circuit_id)
    if not circuit_data:
        return JSONResponse(content={"error": "Circuito no encontrado"}, status_code=404)
    gerber = PCBRenderer().generate_gerber_files(circuit_data)
    return JSONResponse(content=gerber)


@router.post("/{device_name}/generate-firmware")
async def generate_firmware_for_device(device_name: str, request: FirmwareRequest = None):
    from api.app_state import job_queue, jobs
    from agent.agents.hardware_agent import get_hardware_agent
    from tools.firmware_flasher import compile_firmware

    circuit = hardware_memory.get_circuit_context(device_name)
    if not circuit:
        raise HTTPException(status_code=404, detail="No hay circuito guardado para este dispositivo")

    hw_agent            = get_hardware_agent()
    circuit_description = hw_agent._format_circuit_for_firmware(circuit)

    # Detectar plataforma y si es MicroPython
    registered = hardware_memory.get_device_info(device_name)
    is_micropython = bool(registered and registered.get("micropython"))

    if is_micropython:
        platform = "micropython"
    elif "pico" in device_name.lower():
        platform = "rp2040:rp2040"
        is_micropython = True
    elif "esp32" in device_name.lower():
        platform = "esp32:esp32"
    elif "esp8266" in device_name.lower():
        platform = "esp8266:esp8266"
    else:
        platform = "arduino:avr"

    task_desc   = request.task_description if request else "Generar firmware"
    MAX_RETRIES = 3

    def _generate_and_compile():
        # Recuperar errores históricos de este device para contexto preventivo
        past_errors = hardware_memory.get_recent_failures(device_name, limit=3)
        last_error  = ""

        for attempt in range(1, MAX_RETRIES + 1):
            logger.info(f"[Firmware] Intento {attempt}/{MAX_RETRIES} — device={device_name}")

            fw = generate_firmware(
                f"{task_desc}\n\n{circuit_description}",
                platform,
                device_name,
                past_errors=past_errors if attempt == 1 else [],
                compile_error=last_error,
            )
            if "error" in fw:
                raise RuntimeError(fw["error"])

            if is_micropython:
                from tools.firmware_flasher import flash_micropython
                port = registered.get("port", "") if registered else ""
                comp = flash_micropython(fw["path"], port) if port else {
                    "success": True, "output": "Firmware generado (sin puerto para flash)", "error": ""
                }
            else:
                comp = compile_firmware(fw["dir"], platform)

            if comp["success"]:
                logger.info(f"[Firmware] Compilación exitosa en intento {attempt}")
                return {
                    "success":         True,
                    "firmware_path":   fw["path"],
                    "code":            fw["code"],
                    "compile_output":  "Compilación exitosa",
                    "device_name":     device_name,
                    "circuit_project": circuit.get("project_name", "Sin nombre"),
                    "platform":        platform,
                    "attempts":        attempt,
                }

            # Guardar el fallo en historial para aprendizaje futuro
            hardware_memory.save_firmware(
                device_name, task_desc, fw["code"], fw["filename"],
                success=False, serial_out=comp.get("output", "")[:1000],
            )
            last_error = comp.get("output", "")
            logger.warning(f"[Firmware] Intento {attempt} falló — reintentando con error como contexto")

        # Todos los intentos fallaron
        return {
            "success":         False,
            "firmware_path":   fw.get("path", ""),
            "code":            fw.get("code", ""),
            "compile_output":  last_error,
            "device_name":     device_name,
            "circuit_project": circuit.get("project_name", "Sin nombre"),
            "platform":        platform,
            "attempts":        MAX_RETRIES,
        }

    job_id = str(uuid_lib.uuid4())
    jobs[job_id] = {
        "job_id":      job_id,
        "type":        "generate_firmware",
        "status":      "pending",
        "progress":    0,
        "result":      None,
        "error":       None,
        "created_at":  datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
    }
    await job_queue.put({
        "job_id":   job_id,
        "type":     "generate_firmware",
        "_fn":      _generate_and_compile,
        "_args":    (),
        "_kwargs":  {},
    })

    return JSONResponse(content={"job_id": job_id, "status": "pending"})


@router.put("/{circuit_id}/layout")
async def update_circuit_layout(circuit_id: int, body: dict):
    """
    Guarda posiciones personalizadas de componentes en el metadata del circuito.
    Body: { "positions": { "comp_id": {"x": 100, "y": 200}, ... } }
    """
    agent = _get_circuit_agent()
    positions = body.get("positions", {})
    if not isinstance(positions, dict):
        raise HTTPException(status_code=400, detail="positions debe ser un objeto JSON")
    success = agent.circuit_manager.update_layout(circuit_id, positions)
    if not success:
        raise HTTPException(status_code=404, detail="Circuito no encontrado")
    return {"status": "ok", "circuit_id": circuit_id, "positions_saved": len(positions)}


@router.get("/wokwi/status")
async def wokwi_status():
    """Estado del entorno Wokwi CLI: disponibilidad del binario y token configurado."""
    from tools.wokwi_simulator import _is_wokwi_cli_available
    import os
    cli_available = await asyncio.to_thread(_is_wokwi_cli_available)
    token_set = bool(os.getenv("WOKWI_CLI_TOKEN", "").strip())
    return {
        "cli_available": cli_available,
        "token_set": token_set,
        "ready": cli_available and token_set,
        "install_hint": "npm install -g @wokwi/cli  (requiere Node.js)",
        "token_hint": "Obtener en https://wokwi.com/dashboard/ci → API Token, luego WOKWI_CLI_TOKEN=... en .env",
    }


@router.get("/{circuit_id}/diagram.json")
async def download_wokwi_diagram(circuit_id: int):
    """Descarga el diagram.json Wokwi listo para importar en wokwi.com."""
    from tools.wokwi_simulator import generate_wokwi_diagram
    import json as _json

    agent        = _get_circuit_agent()
    circuit_data = agent.get_circuit_by_id(circuit_id)
    if not circuit_data:
        raise HTTPException(status_code=404, detail="Circuito no encontrado")

    diagram  = generate_wokwi_diagram(circuit_data)
    filename = f"stratum_circuit_{circuit_id}.diagram.json"
    return Response(
        content=_json.dumps(diagram, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/{circuit_id}/simulate")
async def simulate_circuit(circuit_id: int, firmware_path: str = "", timeout: int = 10):
    """
    Genera un diagram.json Wokwi para el circuito y opcionalmente lo simula con wokwi-cli.

    - Si wokwi-cli no está disponible: retorna diagram_json listo para cargar en wokwi.com
    - Si wokwi-cli está disponible y WOKWI_CLI_TOKEN está configurado: corre la simulación
    """
    from tools.wokwi_simulator import generate_wokwi_diagram, run_wokwi_cli, get_simulation_url

    agent        = _get_circuit_agent()
    circuit_data = agent.get_circuit_by_id(circuit_id)
    if not circuit_data:
        raise HTTPException(status_code=404, detail="Circuito no encontrado")

    diagram = generate_wokwi_diagram(circuit_data)
    result  = await asyncio.to_thread(run_wokwi_cli, diagram, firmware_path, timeout)
    result["simulation_url"] = get_simulation_url(circuit_data.get("name", "circuit"))
    result["circuit_id"]     = circuit_id
    result["circuit_name"]   = circuit_data.get("name", "")
    return JSONResponse(content=result)


@router.post("/parse-async")
@limiter.limit("5/minute")
async def parse_circuit_async(request: Request, description: str, mcu: str = "Arduino Uno"):
    """Versión async de parse_circuit que retorna job_id inmediatamente."""
    from api.app_state import job_queue, jobs

    agent = _get_circuit_agent()

    job_id = str(uuid_lib.uuid4())
    jobs[job_id] = {
        "job_id":      job_id,
        "type":        "parse_circuit",
        "status":      "pending",
        "progress":    0,
        "result":      None,
        "error":       None,
        "created_at":  datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
    }
    await job_queue.put({
        "job_id":  job_id,
        "type":    "parse_circuit",
        "_fn":     agent.parse_circuit,
        "_args":   (description, mcu),
        "_kwargs": {},
    })

    return JSONResponse(content={"job_id": job_id, "status": "pending"})


# ── DRC ───────────────────────────────────────────────────────────────────────

@router.get("/{circuit_id}/drc")
async def run_circuit_drc(circuit_id: int):
    """Ejecuta el DRC (Design Rule Check) eléctrico sobre un circuito."""
    from tools.electrical_drc import run_drc

    agent        = _get_circuit_agent()
    circuit_data = agent.get_circuit_by_id(circuit_id)
    if not circuit_data:
        raise HTTPException(status_code=404, detail="Circuito no encontrado")

    result = run_drc(circuit_data)
    result["circuit_id"]   = circuit_id
    result["circuit_name"] = circuit_data.get("name", "")
    return JSONResponse(content=result)


# ── BOM ───────────────────────────────────────────────────────────────────────

@router.get("/{circuit_id}/bom")
async def get_circuit_bom(circuit_id: int):
    """Genera el BOM con costos del stock."""
    from tools.bom_generator import generate_bom
    from database.component_stock import get_stock_db

    agent        = _get_circuit_agent()
    circuit_data = agent.get_circuit_by_id(circuit_id)
    if not circuit_data:
        raise HTTPException(status_code=404, detail="Circuito no encontrado")

    bom = generate_bom(circuit_data, get_stock_db().get_all())
    bom["circuit_id"] = circuit_id
    return JSONResponse(content=bom)


@router.get("/{circuit_id}/bom.csv")
async def get_circuit_bom_csv(circuit_id: int):
    """Descarga el BOM como CSV."""
    from tools.bom_generator import generate_bom, bom_to_csv
    from database.component_stock import get_stock_db

    agent        = _get_circuit_agent()
    circuit_data = agent.get_circuit_by_id(circuit_id)
    if not circuit_data:
        raise HTTPException(status_code=404, detail="Circuito no encontrado")

    bom = generate_bom(circuit_data, get_stock_db().get_all())
    csv_content = bom_to_csv(bom)
    cname = (circuit_data.get("name") or "circuit").replace(" ", "_")
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=bom_{cname}_{circuit_id}.csv"},
    )
