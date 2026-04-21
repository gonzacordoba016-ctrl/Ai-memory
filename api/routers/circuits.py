# api/routers/circuits.py
# Circuit Router: parseo de circuitos, esquemáticos SVG, breadboard 3D, PCB, Gerber, firmware

import asyncio
import uuid as uuid_lib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Query, UploadFile, File
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


@router.get("/")
async def list_circuits(user_id: str = Depends(get_current_user)):
    """Lista todos los circuitos del usuario autenticado."""
    agent   = _get_circuit_agent()
    designs = agent.circuit_manager.list_designs(user_id)
    return JSONResponse(content={"circuits": designs, "total": len(designs)})


@router.post("/parse")
@limiter.limit("5/minute")
async def parse_circuit(request: Request, description: str, mcu: str = "Arduino Uno",
                        user_id: str = Depends(get_current_user)):
    agent  = _get_circuit_agent()
    result = await asyncio.to_thread(agent.parse_circuit, description, mcu)
    if result and result.get("design_id"):
        agent.circuit_manager.update_owner(result["design_id"], user_id)
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
@limiter.limit("5/minute")
async def generate_firmware_for_device(request: Request, device_name: str, body: FirmwareRequest = None):
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

    task_desc   = body.task_description if body else "Generar firmware"
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


@router.put("/{circuit_id}")
async def update_circuit(circuit_id: int, body: dict):
    """
    Actualiza componentes y nets de un circuito desde el editor visual.
    Body: { "components": [...], "nets": [...], "name"?: str, "description"?: str }
    Auto-guarda versión antes de aplicar los cambios.
    """
    agent = _get_circuit_agent()
    if not agent.get_circuit_by_id(circuit_id):
        raise HTTPException(status_code=404, detail="Circuito no encontrado")

    ver = agent.circuit_manager.save_version(circuit_id, reason="pre-edit auto-save")
    if ver < 0:
        raise HTTPException(status_code=500, detail="Error guardando versión previa")

    ok = agent.circuit_manager.update_circuit(
        circuit_id,
        body.get("components", []),
        body.get("nets", []),
        name=body.get("name"),
        description=body.get("description"),
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Error actualizando circuito")

    return JSONResponse(content={"status": "ok", "circuit_id": circuit_id})


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
@limiter.limit("5/minute")
async def simulate_circuit(request: Request, circuit_id: int, firmware_path: str = "", timeout: int = 10):
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
@limiter.limit("10/minute")
async def run_circuit_drc(request: Request, circuit_id: int):
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


@router.get("/{circuit_id}/schematic.kicad_sch")
async def get_kicad_schematic(circuit_id: int):
    """Exporta el circuito como esquemático KiCad v6 (.kicad_sch) — abre directo en KiCad."""
    from tools.kicad_exporter import export_kicad_schematic

    agent        = _get_circuit_agent()
    circuit_data = agent.get_circuit_by_id(circuit_id)
    if not circuit_data:
        raise HTTPException(status_code=404, detail="Circuito no encontrado")

    kicad_str = export_kicad_schematic(circuit_data)
    cname     = (circuit_data.get("name") or "circuit").replace(" ", "_")[:40]
    filename  = f"stratum_{cname}_{circuit_id}.kicad_sch"
    return Response(
        content=kicad_str.encode("utf-8"),
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


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


# ── Feature 1: Import Eagle / KiCad ──────────────────────────────────────────

@router.post("/import")
@limiter.limit("10/minute")
async def import_circuit_file(
    request: Request,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
):
    """
    Importa un circuito desde .kicad_sch (KiCad 6+) o .sch (Eagle XML).
    Retorna el diseño guardado con su ID.
    """
    from tools.circuit_importer import import_circuit_file as _import

    content = (await file.read()).decode("utf-8", errors="replace")
    result  = _import(content, file.filename or "imported")

    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])

    agent     = _get_circuit_agent()
    design_id = agent.circuit_manager.save_design(result, user_id)
    if design_id < 0:
        raise HTTPException(status_code=500, detail="Error guardando el circuito importado")

    result["design_id"] = design_id
    agent.circuit_manager.save_version(design_id, reason="import")
    return JSONResponse(content=result)


# ── Feature 2: Versioning ─────────────────────────────────────────────────────

@router.get("/{circuit_id}/versions")
async def list_circuit_versions(circuit_id: int):
    """Lista todas las versiones guardadas de un circuito con diff."""
    agent    = _get_circuit_agent()
    versions = agent.circuit_manager.get_versions(circuit_id)
    return JSONResponse(content={"circuit_id": circuit_id, "versions": versions})


@router.get("/{circuit_id}/versions/{version}")
async def get_circuit_version(circuit_id: int, version: int):
    """Obtiene el snapshot completo de una versión específica."""
    agent = _get_circuit_agent()
    snap  = agent.circuit_manager.get_version_snapshot(circuit_id, version)
    if snap is None:
        raise HTTPException(status_code=404, detail=f"Versión {version} no encontrada")
    return JSONResponse(content=snap)


@router.post("/{circuit_id}/versions/save")
async def save_circuit_version(circuit_id: int, reason: str = "manual"):
    """Guarda manualmente un snapshot de la versión actual."""
    agent = _get_circuit_agent()
    ver   = agent.circuit_manager.save_version(circuit_id, reason=reason)
    if ver < 0:
        raise HTTPException(status_code=404, detail="Circuito no encontrado")
    return JSONResponse(content={"circuit_id": circuit_id, "version": ver, "reason": reason})


@router.post("/{circuit_id}/restore/{version}")
async def restore_circuit_version(circuit_id: int, version: int):
    """Restaura el circuito a una versión anterior (guarda la actual primero)."""
    agent   = _get_circuit_agent()
    success = agent.circuit_manager.restore_to_version(circuit_id, version)
    if not success:
        raise HTTPException(status_code=404, detail="Versión o circuito no encontrado")
    return JSONResponse(content={"circuit_id": circuit_id, "restored_to": version, "status": "ok"})


# ── Feature 3: Share via public link ─────────────────────────────────────────

@router.post("/{circuit_id}/share")
async def share_circuit(circuit_id: int, request: Request):
    """Genera un link público de solo-lectura para el circuito."""
    agent   = _get_circuit_agent()
    circuit = agent.get_circuit_by_id(circuit_id)
    if not circuit:
        raise HTTPException(status_code=404, detail="Circuito no encontrado")

    token   = agent.circuit_manager.create_share(circuit_id)
    if not token:
        raise HTTPException(status_code=500, detail="Error generando token")

    base    = str(request.base_url).rstrip("/")
    url     = f"{base}/api/circuits/shared/{token}"
    viewer  = f"{base}/api/circuits/shared/{token}/viewer"
    return JSONResponse(content={
        "circuit_id": circuit_id,
        "token":      token,
        "url":        url,
        "viewer_url": viewer,
        "message":    "Compartí este link — acceso de solo lectura, sin login requerido",
    })


@router.delete("/{circuit_id}/share")
async def revoke_circuit_share(circuit_id: int):
    """Revoca el link público de un circuito."""
    agent = _get_circuit_agent()
    agent.circuit_manager.revoke_share(circuit_id)
    return JSONResponse(content={"circuit_id": circuit_id, "status": "revoked"})


# Endpoints públicos (sin autenticación) para circuitos compartidos
_public_router = APIRouter(prefix="/api/circuits", tags=["circuits-public"])


@_public_router.get("/shared/{token}")
async def get_shared_circuit(token: str):
    """Retorna los datos de un circuito compartido (read-only, sin auth)."""
    from database.circuit_design import CircuitDesignManager
    mgr  = CircuitDesignManager()
    data = mgr.get_by_share_token(token)
    if not data:
        raise HTTPException(status_code=404, detail="Link inválido o expirado")
    data["shared"] = True
    data["read_only"] = True
    return JSONResponse(content=data)


@_public_router.get("/shared/{token}/viewer", response_class=HTMLResponse)
async def get_shared_viewer(token: str):
    """Abre el viewer de solo-lectura para un circuito compartido."""
    from database.circuit_design import CircuitDesignManager
    mgr  = CircuitDesignManager()
    data = mgr.get_by_share_token(token)
    if not data:
        raise HTTPException(status_code=404, detail="Link inválido o expirado")
    with open("api/static/circuit_viewer.html", "r", encoding="utf-8") as f:
        html = f.read()
    circuit_id = data.get("id", 0)
    # Inject shared token so viewer fetches from /shared/{token} instead of /api/circuits/{id}
    html = html.replace(
        "</head>",
        f'<script>window._SHARED_TOKEN="{token}";window._CIRCUIT_ID={circuit_id};</script>\n</head>',
    )
    return HTMLResponse(html)
