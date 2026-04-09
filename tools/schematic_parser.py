# tools/schematic_parser.py
# Parsers para esquemáticos de herramientas profesionales de EDA
# Soporta: KiCad (.kicad_sch), LTspice (.asc), Eagle (.sch XML)

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Formato interno común
# ─────────────────────────────────────────────────────────────────────────────

def _make_result(source: str, tool: str, components: list, nets: list,
                 raw_description: str = "") -> dict:
    return {
        "source":      source,        # nombre del archivo
        "tool":        tool,          # kicad | ltspice | eagle
        "components":  components,    # lista de dicts {ref, value, description, pins}
        "nets":        nets,          # lista de dicts {name, pins}
        "description": raw_description,
        "component_count": len(components),
        "net_count":       len(nets),
    }


# ─────────────────────────────────────────────────────────────────────────────
# KiCad .kicad_sch  (formato S-expression, KiCad 6+)
# ─────────────────────────────────────────────────────────────────────────────

def parse_kicad(content: str, filename: str = "schematic.kicad_sch") -> dict:
    components = []
    nets = []

    # Extraer símbolos (componentes instanciados)
    # Formato: (symbol (lib_id "...") ... (property "Reference" "R1") (property "Value" "10k") ...)
    symbol_blocks = _extract_sexp_blocks(content, "symbol")
    for block in symbol_blocks:
        ref   = _sexp_property(block, "Reference")
        value = _sexp_property(block, "Value")
        desc  = _sexp_property(block, "Description") or ""
        fp    = _sexp_property(block, "Footprint") or ""

        if not ref or ref.startswith("~"):
            continue

        # Extraer lib_id
        lib_match = re.search(r'\(lib_id\s+"([^"]+)"', block)
        lib_id = lib_match.group(1) if lib_match else ""

        # Extraer pines
        pins = _extract_pins_kicad(block)

        components.append({
            "ref":         ref,
            "value":       value or "",
            "description": desc or lib_id,
            "footprint":   fp,
            "pins":        pins,
        })

    # Extraer nets (etiquetas de red)
    # net_label: (net_label "VCC" ...), (global_label "GND" ...)
    for pattern in [r'\(net_label\s+"([^"]+)"', r'\(global_label\s+"([^"]+)"',
                    r'\(hierarchical_label\s+"([^"]+)"']:
        for m in re.finditer(pattern, content):
            name = m.group(1)
            if not any(n["name"] == name for n in nets):
                nets.append({"name": name, "pins": []})

    description = f"KiCad schematic — {len(components)} componentes, {len(nets)} redes"
    return _make_result(filename, "kicad", components, nets, description)


def _extract_sexp_blocks(content: str, keyword: str) -> list[str]:
    blocks = []
    pattern = rf'\({keyword}\s'
    for m in re.finditer(pattern, content):
        start = m.start()
        depth = 0
        i = start
        while i < len(content):
            if content[i] == '(':
                depth += 1
            elif content[i] == ')':
                depth -= 1
                if depth == 0:
                    blocks.append(content[start:i+1])
                    break
            i += 1
    return blocks


def _sexp_property(block: str, prop_name: str) -> Optional[str]:
    m = re.search(rf'\(property\s+"{re.escape(prop_name)}"\s+"([^"]*)"', block)
    return m.group(1) if m else None


def _extract_pins_kicad(block: str) -> list[str]:
    return re.findall(r'\(pin\s+\w+\s+\w+\s+\(at\s+[\d.\-]+\s+[\d.\-]+[^)]*\)\s+\(length[^)]*\)\s+\(name\s+"([^"]+)"', block)


# ─────────────────────────────────────────────────────────────────────────────
# LTspice .asc
# ─────────────────────────────────────────────────────────────────────────────

def parse_ltspice(content: str, filename: str = "schematic.asc") -> dict:
    components = []
    nets = []

    lines = content.splitlines()
    current_symbol = None

    for line in lines:
        line = line.strip()

        # SYMBOL component x y rotation
        if line.startswith("SYMBOL "):
            parts = line.split()
            sym_name = parts[1] if len(parts) > 1 else "unknown"
            current_symbol = {
                "ref":         "",
                "value":       "",
                "description": sym_name,
                "footprint":   "",
                "pins":        [],
                "_type":       sym_name,
            }

        # SYMATTR InstName R1
        elif line.startswith("SYMATTR InstName") and current_symbol is not None:
            current_symbol["ref"] = line.split(None, 2)[2] if len(line.split()) > 2 else ""

        # SYMATTR Value 10k
        elif line.startswith("SYMATTR Value") and current_symbol is not None:
            current_symbol["value"] = line.split(None, 2)[2] if len(line.split()) > 2 else ""
            # Guardar componente cuando tenemos ref y value
            if current_symbol["ref"]:
                components.append(dict(current_symbol))
            current_symbol = None

        # SYMATTR SpiceModel / otras attrs — ignorar pero no resetear
        elif line.startswith("SYMATTR") and current_symbol is not None:
            pass

        # TEXT para nets / labels
        elif line.startswith("FLAG "):
            parts = line.split()
            if len(parts) >= 4:
                net_name = parts[3]
                if net_name != "0" and not any(n["name"] == net_name for n in nets):
                    nets.append({"name": net_name, "pins": []})

        # WIRE — ignorar coordenadas pero contar conexiones
        elif line.startswith("WIRE "):
            pass

    # Si el último símbolo no se cerró con Value
    if current_symbol and current_symbol["ref"]:
        components.append(current_symbol)

    # GND siempre presente en LTspice
    if not any(n["name"] == "GND" for n in nets):
        nets.append({"name": "GND", "pins": []})

    description = f"LTspice schematic — {len(components)} componentes"
    return _make_result(filename, "ltspice", components, nets, description)


# ─────────────────────────────────────────────────────────────────────────────
# Eagle .sch  (XML)
# ─────────────────────────────────────────────────────────────────────────────

def parse_eagle(content: str, filename: str = "schematic.sch") -> dict:
    components = []
    nets = []

    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        return _make_result(filename, "eagle", [], [], f"Error XML: {e}")

    # Namespace Eagle (algunos archivos usan xmlns)
    ns = ""

    # Buscar instancias de partes en sheets
    for sheet in root.iter(f"{ns}sheet"):
        for instance in sheet.iter(f"{ns}instance"):
            part_name = instance.get("part", "")
            x = instance.get("x", "0")
            y = instance.get("y", "0")

            # Buscar la parte en <parts>
            part_el = root.find(f".//{ns}parts/{ns}part[@name='{part_name}']")
            if part_el is None:
                continue

            ref   = part_el.get("name", part_name)
            value = part_el.get("value", "")
            lib   = part_el.get("library", "")
            dev   = part_el.get("deviceset", "")

            # Atributos extra
            attrs = {}
            for attr in instance.iter(f"{ns}attribute"):
                attrs[attr.get("name", "")] = attr.get("value", "")

            components.append({
                "ref":         ref,
                "value":       value or attrs.get("VALUE", ""),
                "description": f"{lib}/{dev}",
                "footprint":   attrs.get("PACKAGE", ""),
                "pins":        [],
            })

        # Nets
        for net_el in sheet.iter(f"{ns}net"):
            net_name = net_el.get("name", "")
            if net_name and not any(n["name"] == net_name for n in nets):
                # Segmentos y pines conectados
                pins = []
                for pinref in net_el.iter(f"{ns}pinref"):
                    part = pinref.get("part", "")
                    pin  = pinref.get("pin", "")
                    if part and pin:
                        pins.append(f"{part}.{pin}")
                nets.append({"name": net_name, "pins": pins})

    description = f"Eagle schematic — {len(components)} componentes, {len(nets)} redes"
    return _make_result(filename, "eagle", components, nets, description)


# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher principal
# ─────────────────────────────────────────────────────────────────────────────

SUPPORTED_EXTENSIONS = {
    ".kicad_sch": "kicad",
    ".asc":       "ltspice",
    ".sch":       "eagle",
}

def parse_schematic(content: str, filename: str) -> dict:
    """
    Detecta el formato por extensión y parsea el esquemático.
    Retorna dict con: source, tool, components, nets, description, component_count, net_count
    """
    suffix = Path(filename).suffix.lower()

    if suffix == ".kicad_sch":
        return parse_kicad(content, filename)
    elif suffix == ".asc":
        return parse_ltspice(content, filename)
    elif suffix == ".sch":
        # Eagle usa XML; KiCad legacy .sch usa texto diferente
        content_stripped = content.strip()
        if content_stripped.startswith("<?xml") or content_stripped.startswith("<eagle"):
            return parse_eagle(content, filename)
        else:
            # KiCad legacy .sch (v5 y anteriores) — parseo básico
            return _parse_kicad_legacy(content, filename)
    else:
        return _make_result(filename, "unknown", [], [],
                            f"Formato no soportado: {suffix}. Soportados: {', '.join(SUPPORTED_EXTENSIONS)}")


def _parse_kicad_legacy(content: str, filename: str) -> dict:
    """KiCad v5 .sch — formato de texto plano"""
    components = []
    nets = []
    lines = content.splitlines()
    in_comp = False
    current = {}

    for line in lines:
        if line.startswith("$Comp"):
            in_comp = True
            current = {"ref": "", "value": "", "description": "", "footprint": "", "pins": []}
        elif line.startswith("$EndComp"):
            if current.get("ref"):
                components.append(current)
            in_comp = False
        elif in_comp:
            if line.startswith("L "):
                parts = line.split()
                if len(parts) >= 3:
                    current["description"] = parts[1]
                    current["ref"] = parts[2]
            elif line.startswith("F 1 "):
                m = re.search(r'F 1 "([^"]+)"', line)
                if m:
                    current["value"] = m.group(1)
            elif line.startswith("F 2 "):
                m = re.search(r'F 2 "([^"]+)"', line)
                if m:
                    current["footprint"] = m.group(1)
        # Nets en KiCad legacy
        elif line.startswith("Text Label") or line.startswith("Text GLabel"):
            parts = line.split()
            if len(parts) >= 5:
                net_name = parts[-1].strip('"')
                if not any(n["name"] == net_name for n in nets):
                    nets.append({"name": net_name, "pins": []})

    description = f"KiCad v5 schematic — {len(components)} componentes"
    return _make_result(filename, "kicad_legacy", components, nets, description)
