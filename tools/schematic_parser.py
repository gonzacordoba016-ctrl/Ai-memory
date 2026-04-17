# tools/schematic_parser.py
# Parsers para esquemáticos de herramientas profesionales de EDA
# Soporta: KiCad (.kicad_sch), LTspice (.asc), Eagle (.sch XML)

import re
import math
import xml.etree.ElementTree as ET
from collections import defaultdict
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
    """
    Parsea un esquemático KiCad 6+ (.kicad_sch) con conectividad real.

    Algoritmo:
      1. Extrae posiciones de pines desde lib_symbols
      2. Calcula coordenadas mundo de cada pin por instancia (posición + rotación)
      3. Extrae wires, junctions y net labels con posición XY
      4. Construye grafos de conectividad con Union-Find (tolerancia 10 u.KiCad)
      5. Pobla cada net con nodos "REF.PIN" (ej: R1.1, LED1.A)
      6. Marca símbolos de power (lib_id "power:*", #PWR, #FLG) como is_power=True
    """
    _TOLE = 0.5   # tolerancia de snap en mm (< mínimo pin-to-pin de 2.54mm; captura endpoints coincidentes)

    # ── 1. Posiciones de pines en lib_symbols ─────────────────────────────────
    # lib_pin_defs: "Device:R" -> {"1": (rx, ry, pin_name), ...}
    lib_pin_defs: dict = {}
    lib_sym_blocks = _extract_sexp_blocks(content, "lib_symbols")
    if lib_sym_blocks:
        for sym_blk in _extract_sexp_blocks(lib_sym_blocks[0], "symbol"):
            nm = re.match(r'\(symbol\s+"([^"]+)"', sym_blk)
            if not nm:
                continue
            # Normalizar a nombre base: "Device:R_1_1" → "Device:R"
            base = re.sub(r'_\d+_\d+$', '', nm.group(1))
            if base not in lib_pin_defs:
                lib_pin_defs[base] = {}
            for pin_blk in _extract_sexp_blocks(sym_blk, "pin"):
                at_m  = re.search(r'\(at\s+([\d.\-]+)\s+([\d.\-]+)', pin_blk)
                num_m = re.search(r'\(number\s+"([^"]+)"', pin_blk)
                nm_m  = re.search(r'\(name\s+"([^"]+)"', pin_blk)
                if at_m and num_m:
                    rx, ry   = float(at_m.group(1)), float(at_m.group(2))
                    pin_num  = num_m.group(1)
                    pin_name = nm_m.group(1) if nm_m else pin_num
                    lib_pin_defs[base][pin_num] = (rx, ry, pin_name)

    # ── 2. Símbolos instanciados ──────────────────────────────────────────────
    components: list = []
    symbol_pins_xy: dict = {}   # ref -> {pin_num: (wx, wy, pin_name)}

    for block in _extract_sexp_blocks(content, "symbol"):
        if "(lib_id" not in block:
            continue                         # saltar definiciones de lib_symbols
        ref   = _sexp_property(block, "Reference")
        value = _sexp_property(block, "Value")
        desc  = _sexp_property(block, "Description") or ""
        fp    = _sexp_property(block, "Footprint") or ""
        if not ref or ref.startswith("~"):
            continue

        lib_m  = re.search(r'\(lib_id\s+"([^"]+)"', block)
        lib_id = lib_m.group(1) if lib_m else ""
        at_m   = re.search(r'\(at\s+([\d.\-]+)\s+([\d.\-]+)(?:\s+([\d.\-]+))?', block)
        inst_x = float(at_m.group(1)) if at_m else 0.0
        inst_y = float(at_m.group(2)) if at_m else 0.0
        inst_a = float(at_m.group(3)) if (at_m and at_m.group(3)) else 0.0

        is_power = (lib_id.startswith("power:") or
                    ref.startswith("#PWR") or ref.startswith("#FLG"))

        # Calcular coordenadas mundo de pines (rotación KiCad = sentido horario)
        pin_positions: dict = {}
        lib_key = lib_id
        if lib_key not in lib_pin_defs:
            short = lib_id.split(":")[-1] if ":" in lib_id else lib_id
            lib_key = short if short in lib_pin_defs else lib_id
        if lib_key in lib_pin_defs:
            rad = math.radians(-inst_a)
            ca, sa = math.cos(rad), math.sin(rad)
            for pnum, (rx, ry, pname) in lib_pin_defs[lib_key].items():
                wx = inst_x + rx * ca - ry * sa
                wy = inst_y + rx * sa + ry * ca
                pin_positions[pnum] = (wx, wy, pname)

        symbol_pins_xy[ref] = pin_positions
        components.append({
            "ref":         ref,
            "value":       value or "",
            "description": desc or lib_id,
            "footprint":   fp,
            "pins":        list(pin_positions.keys()),
            "is_power":    is_power,
        })

    # ── 3. Wires ──────────────────────────────────────────────────────────────
    wire_segments: list = []
    for wire_blk in _extract_sexp_blocks(content, "wire"):
        s = re.search(r'\(start\s+([\d.\-]+)\s+([\d.\-]+)\)', wire_blk)
        e = re.search(r'\(end\s+([\d.\-]+)\s+([\d.\-]+)\)', wire_blk)
        if s and e:
            wire_segments.append((
                float(s.group(1)), float(s.group(2)),
                float(e.group(1)), float(e.group(2)),
            ))

    # ── 4. Junctions ──────────────────────────────────────────────────────────
    junctions: list = [
        (float(m.group(1)), float(m.group(2)))
        for m in re.finditer(r'\(junction\s+\(at\s+([\d.\-]+)\s+([\d.\-]+)\)', content)
    ]

    # ── 5. Net labels con posición ────────────────────────────────────────────
    label_pos: list = []   # [(name, x, y)]
    for pat in [
        r'\(net_label\s+"([^"]+)"\s+\(at\s+([\d.\-]+)\s+([\d.\-]+)',
        r'\(global_label\s+"([^"]+)"\s+\(at\s+([\d.\-]+)\s+([\d.\-]+)',
        r'\(hierarchical_label\s+"([^"]+)"\s+\(at\s+([\d.\-]+)\s+([\d.\-]+)',
    ]:
        for m in re.finditer(pat, content):
            label_pos.append((m.group(1), float(m.group(2)), float(m.group(3))))

    # ── 6. Union-Find sobre todos los puntos ──────────────────────────────────
    pts: list = []              # (x, y, role, meta)
    wire_idx_pairs: list = []   # pares de índices a unir por pertenencia al mismo wire

    for x1, y1, x2, y2 in wire_segments:
        i1, i2 = len(pts), len(pts) + 1
        pts.append((x1, y1, 'wire', None))
        pts.append((x2, y2, 'wire', None))
        wire_idx_pairs.append((i1, i2))

    for lname, lx, ly in label_pos:
        pts.append((lx, ly, 'label', lname))

    for ref, pd in symbol_pins_xy.items():
        for pnum, (wx, wy, _) in pd.items():
            pts.append((wx, wy, 'pin', f"{ref}.{pnum}"))

    for jx, jy in junctions:
        pts.append((jx, jy, 'junction', None))

    N = len(pts)
    parent = list(range(N))

    def _find(i: int) -> int:
        r = i
        while parent[r] != r:
            r = parent[r]
        while parent[i] != r:
            parent[i], i = r, parent[i]
        return r

    def _union(a: int, b: int) -> None:
        ra, rb = _find(a), _find(b)
        if ra != rb:
            parent[ra] = rb

    for i1, i2 in wire_idx_pairs:
        _union(i1, i2)

    for i in range(N):
        xi, yi = pts[i][0], pts[i][1]
        for j in range(i + 1, N):
            if abs(xi - pts[j][0]) <= _TOLE and abs(yi - pts[j][1]) <= _TOLE:
                _union(i, j)

    # ── 7. Agrupar puntos en nets ─────────────────────────────────────────────
    groups: dict = defaultdict(lambda: {"labels": [], "nodes": []})
    for i, (_, _, role, meta) in enumerate(pts):
        root = _find(i)
        if role == "label" and meta and meta not in groups[root]["labels"]:
            groups[root]["labels"].append(meta)
        elif role == "pin" and meta and meta not in groups[root]["nodes"]:
            groups[root]["nodes"].append(meta)

    # ── 8. Construir lista de nets ────────────────────────────────────────────
    nets: list = []
    seen_labels: set = set()
    for root, data in groups.items():
        if not data["labels"] and not data["nodes"]:
            continue
        name = data["labels"][0] if data["labels"] else f"Net_{root}"
        seen_labels.update(data["labels"])
        nets.append({
            "name":  name,
            "nodes": data["nodes"],
            "pins":  data["nodes"],   # compatibilidad con código anterior
        })
    # Labels sin conexión a wires/pines
    for lname, _, _ in label_pos:
        if lname not in seen_labels and not any(n["name"] == lname for n in nets):
            nets.append({"name": lname, "nodes": [], "pins": []})

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

    # Detectar namespace Eagle si existe (ej: {http://eagle.autodesk.com/xml}eagle)
    tag = root.tag
    ns = tag[:tag.rfind('}')+1] if '}' in tag else ""

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
    """
    KiCad v5 .sch — Union-Find connectivity tracing.

    Format:
      Wire Wire Line          → next line: \tX1 Y1 X2 Y2  (mils)
      Connection ~ X Y        → junction
      Text Label X Y ...\nNAME → net label (name on next line)
      $Comp … P X Y … $EndComp → component; position P X Y used as pin fallback
    """
    _TOLE = 25   # mils tolerance (~0.635 mm, half of 50-mil grid step)

    lines = content.splitlines()

    # ── 1. Components ─────────────────────────────────────────────────────────
    components: list = []
    comp_positions: dict = {}   # ref -> (cx, cy)
    in_comp = False
    current: dict = {}

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("$Comp"):
            in_comp = True
            current = {"ref": "", "value": "", "description": "",
                       "footprint": "", "pins": [], "_x": 0, "_y": 0}
        elif stripped.startswith("$EndComp"):
            if current.get("ref"):
                comp_positions[current["ref"]] = (current["_x"], current["_y"])
                components.append({k: v for k, v in current.items()
                                   if not k.startswith("_")})
            in_comp = False
        elif in_comp:
            if stripped.startswith("L "):
                parts = stripped.split()
                if len(parts) >= 3:
                    current["description"] = parts[1]
                    current["ref"] = parts[2]
            elif stripped.startswith("F 1 "):
                m = re.search(r'F 1 "([^"]+)"', stripped)
                if m:
                    current["value"] = m.group(1)
            elif stripped.startswith("F 2 "):
                m = re.search(r'F 2 "([^"]+)"', stripped)
                if m:
                    current["footprint"] = m.group(1)
            elif stripped.startswith("P "):
                parts = stripped.split()
                if len(parts) >= 3:
                    try:
                        current["_x"] = int(parts[1])
                        current["_y"] = int(parts[2])
                    except ValueError:
                        pass

    # ── 2. Wire segments ──────────────────────────────────────────────────────
    wire_segments: list = []   # [(x1, y1, x2, y2)]
    i = 0
    while i < len(lines):
        if lines[i].strip() == "Wire Wire Line":
            if i + 1 < len(lines):
                parts = lines[i + 1].strip().split()
                if len(parts) == 4:
                    try:
                        x1, y1, x2, y2 = (int(parts[0]), int(parts[1]),
                                           int(parts[2]), int(parts[3]))
                        wire_segments.append((x1, y1, x2, y2))
                    except ValueError:
                        pass
        i += 1

    # ── 3. Junctions ──────────────────────────────────────────────────────────
    junctions: list = []
    for line in lines:
        m = re.match(r'Connection\s+~\s+(\d+)\s+(\d+)', line.strip())
        if m:
            junctions.append((int(m.group(1)), int(m.group(2))))

    # ── 4. Net labels (name on the line immediately after the Text … line) ────
    label_pos: list = []   # [(name, x, y)]
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if (stripped.startswith("Text Label ")
                or stripped.startswith("Text GLabel ")
                or stripped.startswith("Text HLabel ")):
            parts = stripped.split()
            if len(parts) >= 4:
                try:
                    lx, ly = int(parts[2]), int(parts[3])
                    if i + 1 < len(lines):
                        name = lines[i + 1].strip()
                        if name and not name.startswith("$") and not name.startswith("Wire"):
                            label_pos.append((name, lx, ly))
                except ValueError:
                    pass
        i += 1

    # ── 5. Union-Find ─────────────────────────────────────────────────────────
    pts: list = []           # (x, y, role, meta)
    wire_pairs: list = []    # (i1, i2) to union

    for x1, y1, x2, y2 in wire_segments:
        i1, i2 = len(pts), len(pts) + 1
        pts.append((x1, y1, 'wire', None))
        pts.append((x2, y2, 'wire', None))
        wire_pairs.append((i1, i2))

    for name, lx, ly in label_pos:
        pts.append((lx, ly, 'label', name))

    for ref, (cx, cy) in comp_positions.items():
        pts.append((cx, cy, 'pin', ref))

    for jx, jy in junctions:
        pts.append((jx, jy, 'junction', None))

    N = len(pts)
    parent = list(range(N))

    def _find(i: int) -> int:
        r = i
        while parent[r] != r:
            r = parent[r]
        while parent[i] != r:
            parent[i], i = r, parent[i]
        return r

    def _union(a: int, b: int) -> None:
        ra, rb = _find(a), _find(b)
        if ra != rb:
            parent[ra] = rb

    for i1, i2 in wire_pairs:
        _union(i1, i2)

    for i in range(N):
        xi, yi = pts[i][0], pts[i][1]
        for j in range(i + 1, N):
            if abs(xi - pts[j][0]) <= _TOLE and abs(yi - pts[j][1]) <= _TOLE:
                _union(i, j)

    # ── 6. Group into nets ────────────────────────────────────────────────────
    groups: dict = defaultdict(lambda: {"labels": [], "nodes": []})
    for i, (_, _, role, meta) in enumerate(pts):
        root = _find(i)
        if role == "label" and meta and meta not in groups[root]["labels"]:
            groups[root]["labels"].append(meta)
        elif role == "pin" and meta and meta not in groups[root]["nodes"]:
            groups[root]["nodes"].append(meta)

    nets: list = []
    seen_labels: set = set()
    for root, data in groups.items():
        if not data["labels"] and not data["nodes"]:
            continue
        name = data["labels"][0] if data["labels"] else f"Net_{root}"
        seen_labels.update(data["labels"])
        nets.append({
            "name":  name,
            "nodes": data["nodes"],
            "pins":  data["nodes"],
        })

    for name, _, _ in label_pos:
        if name not in seen_labels and not any(n["name"] == name for n in nets):
            nets.append({"name": name, "nodes": [], "pins": []})

    description = f"KiCad v5 schematic — {len(components)} componentes, {len(nets)} redes"
    return _make_result(filename, "kicad_legacy", components, nets, description)
