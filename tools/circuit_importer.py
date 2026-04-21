# tools/circuit_importer.py
# Importa circuitos desde archivos Eagle (.sch XML) y KiCad (.kicad_sch S-expression)
# y los convierte al formato interno de Stratum.

import re
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Tuple
from core.logger import get_logger

logger = get_logger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _guess_type(name: str, value: str = "") -> str:
    """Infiere el tipo de componente desde su nombre/referencia."""
    n = name.upper()
    if n.startswith("R"):   return "resistor"
    if n.startswith("C"):   return "capacitor"
    if n.startswith("L"):   return "inductor"
    if n.startswith("D"):   return "diode"
    if n.startswith("Q"):   return "transistor_npn"
    if n.startswith("U"):   return "ic_generic"
    if n.startswith("SW") or n.startswith("S"): return "button"
    if n.startswith("LED"): return "led"
    if n.startswith("J") or n.startswith("P"):  return "connector"
    if n.startswith("M"):   return "motor"
    if n.startswith("T"):   return "transformer"
    if n.startswith("F"):   return "fuse"
    return "generic"


# ── KiCad S-expression parser ─────────────────────────────────────────────────

def _parse_kicad_sexp(text: str) -> List[Any]:
    """Parser recursivo mínimo de S-expressions KiCad."""
    tokens = re.findall(r'"(?:[^"\\]|\\.)*"|\(|\)|[^\s()]+', text)
    pos = [0]

    def parse_atom(tok: str):
        if tok.startswith('"'):
            return tok[1:-1].replace('\\"', '"')
        try:
            return float(tok) if '.' in tok else int(tok)
        except ValueError:
            return tok

    def parse_expr():
        token = tokens[pos[0]]
        pos[0] += 1
        if token == '(':
            lst = []
            while tokens[pos[0]] != ')':
                lst.append(parse_expr())
            pos[0] += 1  # consume ')'
            return lst
        return parse_atom(token)

    results = []
    while pos[0] < len(tokens):
        results.append(parse_expr())
    return results


def _sexp_find(node: list, key: str) -> List[list]:
    """Encuentra todos los nodos hijo con un nombre dado."""
    if not isinstance(node, list):
        return []
    results = []
    for child in node:
        if isinstance(child, list) and child and child[0] == key:
            results.append(child)
    return results


def _sexp_attr(node: list, key: str, default=None):
    """Obtiene el primer valor de un nodo hijo con nombre dado."""
    found = _sexp_find(node, key)
    if found and len(found[0]) > 1:
        return found[0][1]
    return default


def import_kicad(content: str, filename: str = "imported") -> Dict[str, Any]:
    """
    Parsea un archivo .kicad_sch (KiCad 6/7/8 S-expression) y retorna
    el dict interno de Stratum.
    """
    try:
        tree = _parse_kicad_sexp(content)
        root = tree[0] if tree else []

        if not root or root[0] != "kicad_sch":
            raise ValueError("No es un archivo kicad_sch válido")

        # ── Componentes (symbols instanciados) ────────────────────────────────
        components: List[Dict] = []
        seen_refs: set = set()

        for sym in _sexp_find(root, "symbol"):
            # Buscar propiedad Reference
            ref = None
            value_str = ""
            for prop in _sexp_find(sym, "property"):
                if len(prop) >= 3 and prop[1] == "Reference":
                    ref = prop[2]
                elif len(prop) >= 3 and prop[1] == "Value":
                    value_str = str(prop[2])

            if not ref or ref in seen_refs:
                continue
            # Excluir power symbols (#PWR, #FLG, etc.)
            if ref.startswith("#"):
                continue
            seen_refs.add(ref)

            lib_id = _sexp_attr(sym, "lib_id") or ""
            # lib_id like "Device:R" → use part after colon
            lib_part = lib_id.split(":")[-1] if ":" in lib_id else lib_id

            ctype = _guess_type(ref, value_str)

            components.append({
                "id": ref,
                "name": f"{lib_part} {value_str}".strip() or ref,
                "type": ctype,
                "resolved_type": ctype,
                "value": value_str,
                "unit": "",
            })

        # ── Nets (net_label, global_label) ────────────────────────────────────
        nets: List[Dict] = []
        net_map: Dict[str, List[str]] = {}

        for label in _sexp_find(root, "net_label") + _sexp_find(root, "global_label"):
            name = label[1] if len(label) > 1 else "NET"
            if isinstance(name, str) and name not in net_map:
                net_map[name] = []

        # Build simple nets from net_labels — nodes can't be inferred without
        # full wire-tracing, so we create placeholder nets.
        for name in net_map:
            nets.append({"name": name, "nodes": []})

        # If no nets found, add standard power nets
        if not nets:
            nets = [
                {"name": "VCC", "nodes": []},
                {"name": "GND", "nodes": []},
            ]

        # ── Title block ───────────────────────────────────────────────────────
        title = filename.replace(".kicad_sch", "")
        for tb_prop in _sexp_find(root, "title_block"):
            t = _sexp_attr(tb_prop, "title")
            if t:
                title = str(t)

        return {
            "name": title,
            "description": f"Importado desde {filename}",
            "components": components,
            "nets": nets,
            "power": "Ver esquemático original",
            "warnings": [f"Importado desde KiCad — {len(components)} componentes, {len(nets)} nets"],
            "source_format": "kicad",
            "source_file": filename,
        }

    except Exception as e:
        logger.error(f"[Importer] Error parseando KiCad: {e}")
        return {"error": f"Error parseando KiCad: {e}"}


# ── Eagle XML parser ──────────────────────────────────────────────────────────

def import_eagle(content: str, filename: str = "imported") -> Dict[str, Any]:
    """
    Parsea un archivo .sch de Eagle (XML) y retorna el dict interno de Stratum.
    """
    try:
        root = ET.fromstring(content)
        ns = {"e": ""}  # Eagle no usa namespace

        # Eagle schematics: eagle > drawing > schematic
        schematic = root.find(".//schematic")
        if schematic is None:
            schematic = root  # algunos archivos tienen raíz plana

        # ── Parts ─────────────────────────────────────────────────────────────
        components: List[Dict] = []
        for part in schematic.findall(".//part"):
            ref = part.get("name", "")
            if not ref or ref.startswith("#"):
                continue
            value_str = part.get("value", "")
            deviceset = part.get("deviceset", "")
            ctype = _guess_type(ref, value_str)

            components.append({
                "id": ref,
                "name": f"{deviceset} {value_str}".strip() or ref,
                "type": ctype,
                "resolved_type": ctype,
                "value": value_str,
                "unit": "",
            })

        # ── Nets ──────────────────────────────────────────────────────────────
        nets: List[Dict] = []
        for net in schematic.findall(".//net"):
            net_name = net.get("name", "NET")
            nodes = []
            for pinref in net.findall(".//pinref"):
                part_ref = pinref.get("part", "")
                pin = pinref.get("pin", "")
                if part_ref and pin:
                    nodes.append(f"{part_ref}.{pin}")
            nets.append({"name": net_name, "nodes": nodes})

        if not nets:
            nets = [{"name": "VCC", "nodes": []}, {"name": "GND", "nodes": []}]

        # ── Title ─────────────────────────────────────────────────────────────
        title = filename.replace(".sch", "")
        desc_el = root.find(".//description")
        description = desc_el.text.strip() if desc_el is not None and desc_el.text else ""

        return {
            "name": title,
            "description": description or f"Importado desde {filename}",
            "components": components,
            "nets": nets,
            "power": "Ver esquemático original",
            "warnings": [f"Importado desde Eagle — {len(components)} componentes, {len(nets)} nets"],
            "source_format": "eagle",
            "source_file": filename,
        }

    except ET.ParseError as e:
        logger.error(f"[Importer] Eagle XML inválido: {e}")
        return {"error": f"XML inválido: {e}"}
    except Exception as e:
        logger.error(f"[Importer] Error parseando Eagle: {e}")
        return {"error": f"Error parseando Eagle: {e}"}


# ── Dispatcher ────────────────────────────────────────────────────────────────

def import_circuit_file(content: str, filename: str) -> Dict[str, Any]:
    """
    Detecta el formato y despacha al parser correcto.
    Soporta: .kicad_sch (KiCad 6+), .sch (Eagle XML o KiCad 5 legado).
    """
    fname_lower = filename.lower()

    if fname_lower.endswith(".kicad_sch"):
        return import_kicad(content, filename)

    if fname_lower.endswith(".sch"):
        # Distinguish Eagle XML from KiCad 5 legacy (starts with EESchema)
        stripped = content.lstrip()
        if stripped.startswith("<?xml") or stripped.startswith("<eagle"):
            return import_eagle(content, filename)
        # KiCad 5 legacy format (EESchema Schematic File)
        if "EESchema" in content[:50]:
            return {"error": "KiCad 5 (.sch) no soportado — exportá a KiCad 6+ (.kicad_sch) primero"}
        # Try Eagle anyway
        try:
            return import_eagle(content, filename)
        except Exception:
            return {"error": "Formato no reconocido — usá .kicad_sch (KiCad 6+) o .sch (Eagle)"}

    return {"error": f"Extensión no soportada: {filename} — usá .kicad_sch o .sch"}
