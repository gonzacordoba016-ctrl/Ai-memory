# api/routers/schematics.py
# Importación de esquemáticos profesionales: KiCad, LTspice, Eagle

import json
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse

from tools.schematic_parser import parse_schematic, SUPPORTED_EXTENSIONS
from database.circuit_design import CircuitDesignManager as CircuitDesignDB
from database.design_decisions import get_decisions_db

router = APIRouter(prefix="/api/schematics", tags=["schematics"])

_circuit_db = None

def _get_circuit_db():
    global _circuit_db
    if _circuit_db is None:
        _circuit_db = CircuitDesignDB()
    return _circuit_db


@router.post("/import")
async def import_schematic(
    file: UploadFile = File(...),
    project_name: str = Query(default="", description="Nombre del proyecto (opcional, usa el nombre del archivo si vacío)"),
    save_to_memory: bool = Query(default=True, description="Guardar en circuit_designs automáticamente"),
):
    """
    Importa un esquemático desde KiCad (.kicad_sch), LTspice (.asc) o Eagle (.sch).
    Extrae componentes y redes, y opcionalmente lo guarda en la memoria de circuitos.
    """
    filename = file.filename or "schematic"
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if suffix not in SUPPORTED_EXTENSIONS and not filename.endswith(".kicad_sch"):
        raise HTTPException(
            status_code=400,
            detail=f"Formato no soportado: '{suffix}'. Soportados: {', '.join(SUPPORTED_EXTENSIONS.keys())}"
        )

    content_bytes = await file.read()
    try:
        content = content_bytes.decode("utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"No se pudo leer el archivo: {e}")

    parsed = parse_schematic(content, filename)

    if parsed["tool"] == "unknown":
        raise HTTPException(status_code=400, detail=parsed["description"])

    circuit_id = None
    if save_to_memory and parsed["components"]:
        name = project_name or filename.rsplit(".", 1)[0]

        # Convertir al formato interno de circuit_designs
        components_list = [
            {
                "id":    f"C{i}",
                "type":  c.get("description", "Component"),
                "value": c.get("value", ""),
                "ref":   c.get("ref", f"C{i}"),
                "pins":  c.get("pins", []),
            }
            for i, c in enumerate(parsed["components"])
        ]
        nets_list = [
            {"name": n["name"], "connections": n.get("pins", [])}
            for n in parsed["nets"]
        ]
        metadata = {
            "source_tool": parsed["tool"],
            "source_file": filename,
            "imported":    True,
        }

        circuit_id = _get_circuit_db().save_design({
            "name":        name,
            "description": parsed["description"],
            "components":  components_list,
            "nets":        nets_list,
            "metadata":    metadata,
        })

    return {
        "ok":             True,
        "tool":           parsed["tool"],
        "filename":       filename,
        "component_count": parsed["component_count"],
        "net_count":      parsed["net_count"],
        "components":     parsed["components"],
        "nets":           parsed["nets"],
        "circuit_id":     circuit_id,
        "description":    parsed["description"],
    }


@router.post("/plc/parse")
async def parse_plc_ladder(body: dict):
    """
    Parsea lógica ladder desde texto descriptivo (español o inglés).
    Retorna rungs, variables y pseudocódigo Structured Text (IEC 61131-3).

    Body: { "text": "Si el sensor S1 está activo Y B2 presionado, activar M1 con TON 5s" }
    """
    text = body.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Campo 'text' requerido")

    from tools.plc_parser import parse_plc_input
    result = parse_plc_input(text)

    # Guardar en memoria como circuito de tipo PLC
    if result["rung_count"] > 0:
        name = body.get("name", "PLC Program")
        circuit_id = _get_circuit_db().save_design({
            "name":        name,
            "description": f"Lógica Ladder — {result['rung_count']} rungs",
            "components":  [{"id": v, "type": "PLC_Variable", "value": "", "ref": v}
                            for v in result["variables"]],
            "nets":        [],
            "metadata":    {"type": "plc", "ladder": result},
        })
        result["circuit_id"] = circuit_id

    return result


@router.get("/supported")
async def get_supported_formats():
    """Lista los formatos de esquemáticos soportados."""
    return {
        "formats": [
            {"extension": ".kicad_sch", "tool": "KiCad",   "version": "6+"},
            {"extension": ".sch",       "tool": "Eagle",    "version": "XML"},
            {"extension": ".sch",       "tool": "KiCad v5", "version": "legacy"},
            {"extension": ".asc",       "tool": "LTspice",  "version": "XVII+"},
            {"extension": "text",       "tool": "PLC Ladder", "version": "IEC 61131-3"},
        ]
    }
