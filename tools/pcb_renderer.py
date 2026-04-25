# tools/pcb_renderer.py
# PCB layout renderer: SVG visual preview + Gerber RS-274X for fabrication.
# Placement algorithm: group components by function, route traces with simple
# Manhattan segments. Not a full autorouter — gives a meaningful starting point.

from typing import Dict, Any, List, Tuple, Optional
from core.logger import get_logger

logger = get_logger(__name__)

# mm → px at 96 DPI
_MM2PX = 3.7795275591

# Functional groups for placement
_MCU_TYPES   = {"arduino_uno", "arduino_nano", "arduino_mega", "esp32", "esp8266",
                "stm32", "rp2040", "pico", "attiny", "mcu"}
_SMALL_TYPES = {"resistor", "capacitor", "diode", "led", "led_rgb",
                "1n4007", "1n5819", "1n4148", "varistor", "fuse"}
_LARGE_TYPES = {"relay", "relay_module", "ssr", "motor_driver", "l298n", "drv8825",
                "display", "oled", "lcd", "battery", "transformer", "smps"}
_RELAY_TYPES = {"relay", "relay_module", "ssr"}

# F3.2 — industrial footprint dimensions in mm (W × H)
_FOOTPRINT: Dict[str, Tuple[float, float]] = {
    # Passives
    "resistor":     (6.5, 2.5),
    "capacitor":    (3.0, 3.0),
    "capacitor_electrolytic": (8.0, 8.0),
    "led":          (5.0, 5.0),
    "led_rgb":      (5.0, 5.0),
    "diode":        (6.5, 2.5),
    "1n4007":       (6.5, 2.5),
    "1n5819":       (6.5, 2.5),
    "1n4148":       (4.0, 1.6),
    "button":       (6.0, 6.0),
    "buzzer":       (12.0, 12.0),
    "inductor":     (10.0, 10.0),

    # Industrial / power components (F3.2)
    "transformer":      (80.0, 60.0),  # toroidal/EI core
    "smps":             (80.0, 40.0),  # Mean Well style module
    "bridge_rectifier": (8.5, 5.0),    # GBU/KBP package
    "fuse":             (30.0, 14.0),  # 5×20mm fuse + holder
    "fuse_holder":      (30.0, 14.0),
    "varistor":         (10.0, 7.0),   # MOV disc
    "mov":              (10.0, 7.0),
    "voltage_regulator":(10.5, 14.0),  # TO-220 with tab
    "lm7805":           (10.5, 14.0),
    "lm317":            (10.5, 14.0),
    "ams1117":          (5.0, 4.5),    # SOT-223 SMD
    "regulator":        (10.5, 14.0),
    "optoacoplador":    (6.5, 9.0),    # DIP-4
    "pc817":            (6.5, 9.0),
    "ssr":              (45.0, 53.0),  # Fotek SSR-25DA
    "inductor_cm":      (25.0, 20.0),  # common-mode choke
    "x_capacitor":      (15.0, 10.0),  # X2 safety cap

    # Modules
    "relay":        (19.0, 15.5),
    "relay_module": (40.0, 25.0),
    "motor_driver": (35.0, 35.0),
    "oled":         (27.0, 27.0),
    "lcd":          (80.0, 36.0),

    # Connectors
    "connector":      (10.0, 8.0),
    "header":         (5.0, 5.0),
    "pin_header":     (5.0, 5.0),
    "terminal_block": (10.0, 8.0),

    # MCUs
    "arduino_uno":  (68.6, 53.4),
    "arduino_nano": (18.0, 43.2),
    "arduino_mega": (101.5, 53.4),
    "esp32":        (18.0, 25.4),
    "esp8266":      (24.8, 16.0),
    "pico":         (21.0, 51.0),
    "stm32":        (25.4, 25.4),
}

_DEFAULT_FP = (10.0, 8.0)


def _fp(comp_type: str) -> Tuple[float, float]:
    return _FOOTPRINT.get(comp_type.lower(), _DEFAULT_FP)


def _group(comp_type: str) -> str:
    t = comp_type.lower()
    if t in _MCU_TYPES:   return "mcu"
    if t in _SMALL_TYPES: return "small"
    if t in _LARGE_TYPES: return "large"
    return "misc"


# F3 — Zone classification mirroring schematic layout
_ZONE_HV_TYPES = {
    "transformer", "smps", "bridge_rectifier", "fuse", "fuse_holder",
    "varistor", "mov", "inductor_cm", "x_capacitor",
}
_ZONE_MCU_PWR_TYPES = _MCU_TYPES | {
    "voltage_regulator", "lm7805", "ams1117", "lm317", "regulator",
    "buck_converter", "boost_converter", "ldo", "dc_dc",
}


def _pcb_zone(comp: Dict) -> str:
    """Returns 'hv', 'mcu', 'relay', 'output', or 'other'."""
    cid = (comp.get("id", "") or "").lower()
    t = (comp.get("resolved_type") or comp.get("type") or "").lower()
    name = (comp.get("name", "") or "").lower()

    if t in _RELAY_TYPES or cid.startswith("rl"):
        return "relay"
    if t in _ZONE_HV_TYPES:
        return "hv"
    if t == "connector" and (
        cid == "j1" or "220" in name or "110" in name
        or "ac" in name or "input" in name or "entrada" in name
    ):
        return "hv"
    if t in _ZONE_MCU_PWR_TYPES:
        return "mcu"
    if t == "connector":
        return "output"
    return "other"


def _build_pcb_relay_groups(components: List[Dict]) -> Dict[str, List[Dict]]:
    """Same as schematic: pair RLn with its Dn flyback + Rn control resistor."""
    by_id = {c["id"]: c for c in components}
    relay_ids = [
        c["id"] for c in components
        if (c.get("resolved_type") or c.get("type") or "").lower() in _RELAY_TYPES
        or c["id"].lower().startswith("rl")
    ]
    groups: Dict[str, List[Dict]] = {}
    used: set = set()
    for rid in relay_ids:
        if rid in used:
            continue
        cell = [by_id[rid]]
        used.add(rid)
        n_match = "".join(ch for ch in rid if ch.isdigit())
        if n_match:
            for cand in (f"D_fly{n_match}", f"D_fly_{rid}", f"D{n_match}",
                         f"D_flyback_{rid}", f"Dfly{n_match}"):
                if cand in by_id and cand not in used:
                    cell.append(by_id[cand])
                    used.add(cand)
                    break
            for cand in (f"R{n_match}", f"R_ctrl_{rid}", f"Rctrl{n_match}", f"R_{rid}"):
                if cand in by_id and cand not in used:
                    cell.append(by_id[cand])
                    used.add(cand)
                    break
        groups[rid] = cell
    return groups


# ──────────────────────────────────────────────────────────────────────────────
# Placement
# ──────────────────────────────────────────────────────────────────────────────

def _place_components(components: List[Dict],
                      board_w: float, board_h: float,
                      nets: Optional[List[Dict]] = None) -> Dict[str, Tuple[float, float]]:
    """
    F3.1 — 4-zone placement (signal flow left → right):
      Zone HV     (x: 0-30%):   AC input, transformer, rectifier, varistor, SMPS
      Zone MCU    (x: 30-50%):  voltage regulator, MCU, decoupling caps
      Zone Relay  (x: 50-80%):  RL1..RLN in vertical column with Dn + Rn cells
      Zone Output (x: 80-100%): output connectors J2..JN

    Si se pasa `nets`, después del primer pass se ejecuta barycentric Y-reorder
    por zona (3 iteraciones) para minimizar HPWL — i.e. los componentes
    interconectados terminan a alturas similares y los cables cruzan menos.
    """
    positions: Dict[str, Tuple[float, float]] = {}

    relay_groups = _build_pcb_relay_groups(components)
    grouped_ids = {cid for cell in relay_groups.values() for cid in (c["id"] for c in cell)}

    zones: Dict[str, List[Dict]] = {z: [] for z in ("hv", "mcu", "relay", "output", "other")}
    for comp in components:
        if comp["id"] in grouped_ids:
            continue
        zones[_pcb_zone(comp)].append(comp)

    # X bands (centers) — packed: cada zona usa el ancho que necesita + gap fijo,
    # NO fracciones fijas del board (eso dejaba grandes huecos horizontales).
    margin = 5.0
    gap = 12.0  # mm de separación entre zonas
    relay_cell_extra = 22.0  # espacio para el sub-cluster de diodo+resistor a la izq del relay

    def _zone_max_w(zone_comps: List[Dict]) -> float:
        if not zone_comps:
            return 0.0
        return max(_fp(c.get("resolved_type", c.get("type", "")))[0] for c in zone_comps)

    # Anchos REALES de cada columna
    w_hv     = _zone_max_w(zones["hv"])
    w_mcu    = _zone_max_w(zones["mcu"])
    w_other  = _zone_max_w(zones["other"])
    relay_max_w = _zone_max_w([cell[0] for cell in relay_groups.values()]) if relay_groups else 0.0
    w_relay  = (relay_max_w + relay_cell_extra) if relay_max_w else 0.0
    w_output = _zone_max_w(zones["output"])

    # X centers acumulando desde la izquierda
    cur_x = margin + (w_hv / 2 if w_hv else 0)
    x_hv = cur_x
    if w_hv:
        cur_x += w_hv / 2 + gap

    if w_mcu:
        cur_x += w_mcu / 2
        x_mcu = cur_x
        cur_x += w_mcu / 2 + gap
    else:
        x_mcu = cur_x

    if w_other:
        cur_x += w_other / 2
        x_other_zone = cur_x
        cur_x += w_other / 2 + gap
    else:
        x_other_zone = cur_x

    if w_relay:
        cur_x += w_relay / 2
        x_relay = cur_x
        cur_x += w_relay / 2 + gap
    else:
        x_relay = cur_x

    if w_output:
        cur_x += w_output / 2
        x_output = cur_x
        cur_x += w_output / 2
    else:
        x_output = cur_x

    top = margin + 8.0
    bot = board_h - margin - 8.0
    usable = max(bot - top, 1.0)

    def _per_comp_stack(comps_in_zone: List[Dict], pad: float = 4.0) -> List[float]:
        """
        Returns Y-center for each component, packed sequentially.
        Each component reserves its actual footprint height + pad as its slot.
        If total slots exceed usable height, slots scale down uniformly so that
        the column fits inside the board (large parts may then visually overlap,
        but coordinates stay in-bounds — the caller should grow the board first).
        """
        n = len(comps_in_zone)
        if n == 0:
            return []
        slot_heights = []
        for c in comps_in_zone:
            _, h = _fp(c.get("resolved_type", c.get("type", "")))
            slot_heights.append(max(h, 12.0) + pad)
        total = sum(slot_heights)
        scale = 1.0 if total <= usable else usable / total
        # Center the stack vertically inside [top, bot]
        scaled_total = total * scale
        cur = top + (usable - scaled_total) / 2
        centers = []
        for h in slot_heights:
            slot = h * scale
            centers.append(cur + slot / 2)
            cur += slot
        return centers

    # ── Zone HV ──
    hv_comps = zones["hv"]
    for comp, ypos in zip(hv_comps, _per_comp_stack(hv_comps, pad=6.0)):
        positions[comp["id"]] = (x_hv, ypos)

    # ── Zone MCU/Power ──
    mcu_comps = zones["mcu"]
    def _mcu_key(c):
        t = (c.get("resolved_type") or c.get("type") or "").lower()
        return 1 if t in _MCU_TYPES else 0
    mcu_sorted = sorted(mcu_comps, key=_mcu_key)
    for comp, ypos in zip(mcu_sorted, _per_comp_stack(mcu_sorted, pad=6.0)):
        positions[comp["id"]] = (x_mcu, ypos)

    # ── Zone Relay (cells: relay + diode + control resistor) ──
    relay_cells = list(relay_groups.values())
    n_cells = len(relay_cells)
    if n_cells > 0:
        # Each cell takes ~max(relay_h, 26)+6 mm vertically
        relay_h = _fp("relay_module")[1]
        cell_pitch = max(28.0, relay_h + 8.0)
        # Build a stack treating each cell as one "slot"
        cell_slots = [{"resolved_type": "relay_module"}] * n_cells
        cell_y_centers = _per_comp_stack(cell_slots, pad=8.0)
        for cell, cy_c in zip(relay_cells, cell_y_centers):
            relay = cell[0]
            positions[relay["id"]] = (x_relay, cy_c)
            if len(cell) > 1:
                positions[cell[1]["id"]] = (x_relay - 18.0, cy_c - 5.0)
            if len(cell) > 2:
                positions[cell[2]["id"]] = (x_relay - 18.0, cy_c + 5.0)

    # Standalone relays (defensive)
    standalone_relays = [c for c in zones["relay"] if c["id"] not in positions]
    if standalone_relays:
        for comp, ypos in zip(standalone_relays, _per_comp_stack(standalone_relays, pad=8.0)):
            positions[comp["id"]] = (x_relay, ypos)

    # ── Zone Output (connectors stacked) ──
    out_comps = zones["output"]
    for comp, ypos in zip(out_comps, _per_comp_stack(out_comps, pad=6.0)):
        positions[comp["id"]] = (x_output, ypos)

    # ── 'other' / misc — entre MCU y relay zones (X calculado arriba) ──
    other_comps = [c for c in zones["other"] if c["id"] not in positions]
    if other_comps:
        for comp, ypos in zip(other_comps, _per_comp_stack(other_comps, pad=4.0)):
            positions[comp["id"]] = (x_other_zone, ypos)

    # ── HPWL barycentric Y-reorder (3 iters) ──
    # Para cada zona, recalcular el orden Y de los componentes según el promedio
    # de Y de los componentes con los que comparten net (excluyendo los de la
    # misma zona — sólo cuentan conexiones inter-zona porque son las que generan
    # cables largos visibles). La zona más poblada queda como ANCLA y no se
    # reordena: las demás se acomodan a ella.
    if nets:
        # Precomputar adyacencia: id → set de ids con los que comparte alguna net
        adj: Dict[str, set] = {c["id"]: set() for c in components}
        for net in nets:
            ids_in_net = [str(node).split(".")[0] for node in net.get("nodes", [])]
            ids_in_net = [i for i in ids_in_net if i in adj]
            for i in ids_in_net:
                for j in ids_in_net:
                    if i != j:
                        adj[i].add(j)
        # Mapa id → zona (incluye relay-cell members con su zona "relay")
        comp_zone: Dict[str, str] = {}
        for z, lst in zones.items():
            for c in lst:
                comp_zone[c["id"]] = z
        for cell in relay_groups.values():
            for c in cell:
                comp_zone[c["id"]] = "relay"

        # Zona ancla = la más poblada (en componentes ya posicionados)
        zone_pop = {z: len(lst) for z, lst in zones.items()}
        zone_pop["relay"] = max(zone_pop["relay"], len(relay_groups))
        anchor = max(zone_pop, key=lambda z: zone_pop[z])

        # Reorder por barycenter: per-zone, calcular Y target y reasignar Ys de la zona
        def _reorder_zone(zone_name: str, zone_comps: List[Dict], x_center: float,
                           pad: float) -> None:
            if zone_name == anchor or len(zone_comps) < 2:
                return
            targets: List[Tuple[float, Dict]] = []
            for c in zone_comps:
                ys = [positions[nb][1] for nb in adj.get(c["id"], ())
                       if nb in positions and comp_zone.get(nb) != zone_name]
                if ys:
                    targets.append((sum(ys) / len(ys), c))
                else:
                    # Sin conexiones inter-zona: mantener Y actual (orden estable)
                    targets.append((positions[c["id"]][1], c))
            targets.sort(key=lambda t: t[0])
            reordered = [t[1] for t in targets]
            for c, y in zip(reordered, _per_comp_stack(reordered, pad=pad)):
                positions[c["id"]] = (x_center, y)

        for _ in range(3):
            _reorder_zone("hv",     zones["hv"],     x_hv,         6.0)
            _reorder_zone("mcu",    mcu_sorted,      x_mcu,        6.0)
            _reorder_zone("other",  other_comps,     x_other_zone, 4.0)
            _reorder_zone("output", out_comps,       x_output,     6.0)
            # Reorder de RELAY cells (si no es ancla): mover el cluster diodo+R con su relay
            if anchor != "relay" and len(relay_groups) >= 2:
                relay_targets: List[Tuple[float, List[Dict]]] = []
                for cell in relay_cells:
                    relay = cell[0]
                    ys = [positions[nb][1] for nb in adj.get(relay["id"], ())
                           if nb in positions and comp_zone.get(nb) != "relay"]
                    relay_targets.append((sum(ys) / len(ys) if ys else positions[relay["id"]][1], cell))
                relay_targets.sort(key=lambda t: t[0])
                reordered_cells = [t[1] for t in relay_targets]
                cell_slots = [{"resolved_type": "relay_module"}] * len(reordered_cells)
                new_cell_y = _per_comp_stack(cell_slots, pad=8.0)
                for cell, cy in zip(reordered_cells, new_cell_y):
                    relay = cell[0]
                    positions[relay["id"]] = (x_relay, cy)
                    if len(cell) > 1:
                        positions[cell[1]["id"]] = (x_relay - 18.0, cy - 5.0)
                    if len(cell) > 2:
                        positions[cell[2]["id"]] = (x_relay - 18.0, cy + 5.0)

    return positions


# ──────────────────────────────────────────────────────────────────────────────
# Board dimensions
# ──────────────────────────────────────────────────────────────────────────────

def _board_size(components: List[Dict]) -> Tuple[float, float]:
    """
    F3.4 — board size driven by actual zone widths and the largest vertical stack
    (typically the relay column). No hard upper cap — boards grow as needed.
    """
    if not components:
        return (60.0, 50.0)

    # Per-zone widest footprint = zone column requirement
    zone_widths: Dict[str, float] = {z: 0.0 for z in ("hv", "mcu", "relay", "output", "other")}
    zone_count:  Dict[str, int]   = {z: 0   for z in ("hv", "mcu", "relay", "output", "other")}

    for c in components:
        z = _pcb_zone(c)
        w, h = _fp(c.get("resolved_type", c.get("type", "")))
        zone_widths[z] = max(zone_widths[z], w)
        zone_count[z] += 1

    # Sum widths plus inter-zone gaps — solo cuenta zonas con contenido
    gap = 12.0  # mm entre zonas con contenido
    margin = 8.0
    relay_cell_extra = 22.0  # diodo+resistor a la izq del relay
    parts: List[float] = []
    if zone_count["hv"]:     parts.append(zone_widths["hv"])
    if zone_count["mcu"]:    parts.append(zone_widths["mcu"])
    if zone_count["other"]:  parts.append(zone_widths["other"])
    if zone_count["relay"]:  parts.append(zone_widths["relay"] + relay_cell_extra)
    if zone_count["output"]: parts.append(zone_widths["output"])

    total_w = margin * 2 + sum(parts) + gap * max(0, len(parts) - 1)
    total_w = max(total_w, 80.0)  # mínimo razonable

    # Height: driven by the longest zone stack. Mirrors _per_comp_stack pad logic
    # in _place_components so the column fits without negative-Y overflow.
    def _stack_height(zone: str, default_pitch: float, pad: float) -> float:
        comps_in_zone = [c for c in components if _pcb_zone(c) == zone]
        if not comps_in_zone:
            return 0.0
        total = 0.0
        for c in comps_in_zone:
            _, h = _fp(c.get("resolved_type", c.get("type", "")))
            total += max(h, default_pitch) + pad
        return total

    h_hv     = _stack_height("hv",     12.0, 6.0)
    h_mcu    = _stack_height("mcu",    12.0, 6.0)
    # Relay zone: each cell counts as relay_module height + 8 pad
    relay_count = sum(1 for c in components if _pcb_zone(c) == "relay")
    h_relay  = relay_count * (max(_FOOTPRINT.get("relay_module", (40, 25))[1], 28.0) + 8.0)
    h_output = _stack_height("output", 12.0, 6.0)
    h_other  = _stack_height("other",  12.0, 4.0)

    total_h = max(h_hv, h_mcu, h_relay, h_output, h_other) + margin * 2 + 14.0  # +14 for label area
    total_h = max(total_h, 70.0)

    return (round(total_w, 1), round(total_h, 1))


# ──────────────────────────────────────────────────────────────────────────────
# Trace routing (Manhattan, 2-layer)
# ──────────────────────────────────────────────────────────────────────────────

def _route_traces(nets: List[Dict],
                  positions: Dict[str, Tuple[float, float]]) -> List[Dict]:
    """
    Returns a list of trace segments: {x1, y1, x2, y2, net, layer, width}.
    Uses simple Manhattan routing: horizontal then vertical.
    VCC/GND on bottom copper, signals on top copper.
    """
    traces = []
    for net in nets:
        name  = net.get("name", "")
        nodes = net.get("nodes", [])

        is_pwr = any(v in name.lower() for v in ("vcc", "gnd", "5v", "3v3", "vin", "gnd"))
        layer  = "bottom" if is_pwr else "top"
        width  = 1.2 if is_pwr else 0.5

        coords = []
        for node in nodes:
            cid = node.split(".")[0]
            if cid in positions:
                coords.append(positions[cid])

        for i in range(len(coords) - 1):
            x1, y1 = coords[i]
            x2, y2 = coords[i + 1]
            mid_x = (x1 + x2) / 2
            traces.append({"x1": x1, "y1": y1, "x2": mid_x, "y2": y1,
                            "net": name, "layer": layer, "width": width})
            traces.append({"x1": mid_x, "y1": y1, "x2": mid_x, "y2": y2,
                            "net": name, "layer": layer, "width": width})
            traces.append({"x1": mid_x, "y1": y2, "x2": x2, "y2": y2,
                            "net": name, "layer": layer, "width": width})
    return traces


# ──────────────────────────────────────────────────────────────────────────────
# PCBRenderer class
# ──────────────────────────────────────────────────────────────────────────────

class PCBRenderer:
    def __init__(self):
        self.mm2px = _MM2PX

    # ── SVG ───────────────────────────────────────────────────────────────────

    def render_pcb_svg(self, circuit_data: Dict[str, Any]) -> str:
        try:
            components = circuit_data.get("components", [])
            nets       = circuit_data.get("nets", [])
            board_w, board_h = _board_size(components)
            positions  = _place_components(components, board_w, board_h, nets)
            traces     = _route_traces(nets, positions)

            # DRC error component IDs for highlighting
            drc = circuit_data.get("drc", {})
            drc_error_comps = {
                e.get("component", "") for e in drc.get("errors", []) if e.get("component")
            }

            pw = board_w * self.mm2px
            ph = board_h * self.mm2px

            svg = [
                f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'width="{pw:.1f}" height="{ph:.1f}" '
                f'viewBox="0 0 {board_w:.2f} {board_h:.2f}">',
                '<defs>',
                '  <style>',
                '    .board { fill: #1a4a1a; }',
                '    .copper-top { stroke: #daa520; fill: none; }',
                '    .copper-bot { stroke: #b87333; fill: none; }',
                '    .silkscreen { fill: white; font-family: monospace; }',
                '    .pad { fill: #daa520; stroke: #111; stroke-width: 0.2; }',
                '    .pad-gnd { fill: #b87333; stroke: #111; stroke-width: 0.2; }',
                '    .pad-smd { fill: #c8a000; stroke: #111; stroke-width: 0.15; }',
                '    .via { fill: #888; stroke: #daa520; stroke-width: 0.15; }',
                '    .drc-error { stroke: #ff3333 !important; stroke-width: 0.4 !important; }',
                '  </style>',
                '  <filter id="glow">',
                '    <feGaussianBlur stdDeviation="0.3" result="blur"/>',
                '    <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>',
                '  </filter>',
                '</defs>',
                f'<!-- PCB: {circuit_data.get("name","Circuit")} — {len(components)} comps -->',
                f'<rect x="0" y="0" width="{board_w:.2f}" height="{board_h:.2f}" class="board"/>',
                # Courtyard
                f'<rect x="0.5" y="0.5" width="{board_w-1:.2f}" height="{board_h-1:.2f}" '
                f'fill="none" stroke="#ffcc00" stroke-width="0.15" stroke-dasharray="0.5,0.5"/>',
            ]

            # ── F3.3 — HV/LV separation line ─────────────────────────────────
            # Drawn between the HV zone (rightmost HV component) and the MCU zone
            # (leftmost MCU component), with a 3mm clearance band.
            hv_xs = [
                positions[c["id"]][0] + _fp(c.get("resolved_type", c.get("type", "")))[0] / 2
                for c in components
                if c["id"] in positions and _pcb_zone(c) == "hv"
            ]
            mcu_xs = [
                positions[c["id"]][0] - _fp(c.get("resolved_type", c.get("type", "")))[0] / 2
                for c in components
                if c["id"] in positions and _pcb_zone(c) == "mcu"
            ]
            if hv_xs and mcu_xs:
                sep_x = (max(hv_xs) + min(mcu_xs)) / 2
                # Clearance band (semi-transparent red)
                svg.append(
                    f'<rect x="{sep_x-1.5:.3f}" y="2" width="3" height="{board_h-4:.2f}" '
                    f'fill="#aa0000" fill-opacity="0.10" stroke="none"/>'
                )
                # Dashed warning line
                svg.append(
                    f'<line x1="{sep_x:.3f}" y1="2" x2="{sep_x:.3f}" y2="{board_h-2:.2f}" '
                    f'stroke="#ff3300" stroke-width="0.4" stroke-dasharray="1.5,0.8"/>'
                )
                # Zone labels
                svg.append(
                    f'<text x="{sep_x-2.5:.3f}" y="6" font-size="2.2" fill="#ff6633" '
                    f'text-anchor="end" font-family="monospace" font-weight="bold">HV ZONE</text>'
                )
                svg.append(
                    f'<text x="{sep_x+2.5:.3f}" y="6" font-size="2.2" fill="#66ff66" '
                    f'text-anchor="start" font-family="monospace" font-weight="bold">LV ZONE</text>'
                )
                svg.append(
                    f'<text x="{sep_x:.3f}" y="{board_h-3:.2f}" font-size="1.6" fill="#ffaa66" '
                    f'text-anchor="middle" font-family="monospace">⚠ 3mm clearance</text>'
                )

            # ── GND copper pour (hatched zone) ───────────────────────────────
            svg.append('<!-- GND copper pour (hatched) -->')
            gnd_nets = [n for n in nets
                        if "gnd" in n.get("name", "").lower() or "ground" in n.get("name", "").lower()]
            if gnd_nets:
                gnd_comps = set()
                for n in gnd_nets:
                    for node in n.get("nodes", []):
                        gnd_comps.add(node.split(".")[0])
                for cid in gnd_comps:
                    if cid not in positions:
                        continue
                    cx, cy = positions[cid]
                    ctype  = next((c.get("resolved_type", c.get("type", "")) for c in components
                                   if c["id"] == cid), "")
                    w, h   = _fp(ctype)
                    pad_r  = 0.7
                    # Small copper fill near GND pad
                    svg.append(
                        f'<rect x="{cx-w/2-1:.3f}" y="{cy-pad_r:.3f}" '
                        f'width="2" height="{2*pad_r:.3f}" '
                        f'fill="#b87333" fill-opacity="0.3" rx="0.3"/>'
                    )

            # ── Traces ───────────────────────────────────────────────────────
            svg.append('<!-- Copper traces -->')
            via_positions: set[tuple] = set()
            for tr in traces:
                cls   = "copper-bot" if tr["layer"] == "bottom" else "copper-top"
                color = "#b87333" if tr["layer"] == "bottom" else "#daa520"
                svg.append(
                    f'<line x1="{tr["x1"]:.3f}" y1="{tr["y1"]:.3f}" '
                    f'x2="{tr["x2"]:.3f}" y2="{tr["y2"]:.3f}" '
                    f'stroke="{color}" stroke-width="{tr["width"]:.2f}" stroke-linecap="round"/>'
                )
                # Collect midpoints for via placement (where top/bot layers meet)
                if tr["layer"] == "top":
                    via_positions.add((round(tr["x2"], 2), round(tr["y2"], 2)))

            # ── Vias at trace junctions ───────────────────────────────────────
            svg.append('<!-- Vias -->')
            for vx, vy in list(via_positions)[:40]:  # cap to avoid clutter
                svg.append(
                    f'<circle cx="{vx:.3f}" cy="{vy:.3f}" r="0.5" class="via"/>'
                )
                svg.append(
                    f'<circle cx="{vx:.3f}" cy="{vy:.3f}" r="0.25" fill="#111"/>'
                )

            # ── Components ───────────────────────────────────────────────────
            svg.append('<!-- Components -->')
            for comp in components:
                cid    = comp["id"]
                ctype  = comp.get("resolved_type", comp.get("type", "generic")).lower()
                cx, cy = positions.get(cid, (board_w / 2, board_h / 2))
                w, h   = _fp(ctype)
                hw, hh = w / 2, h / 2

                is_drc_error = cid in drc_error_comps
                body_color   = _body_color(ctype)
                border_color = "#ff3333" if is_drc_error else "#daa520"
                border_w     = 0.5 if is_drc_error else 0.2

                # ── Courtyard (dashed yellow rect, 0.5mm clearance per side) ───
                cy_off = 0.5
                svg.append(
                    f'<rect x="{cx-hw-cy_off:.3f}" y="{cy-hh-cy_off:.3f}" '
                    f'width="{w+cy_off*2:.3f}" height="{h+cy_off*2:.3f}" '
                    f'fill="none" stroke="#ffcc00" stroke-width="0.15" '
                    f'stroke-dasharray="0.6,0.4"/>'
                )

                # ── Silkscreen component outline (white, dashed) ──────────────
                svg.append(
                    f'<rect x="{cx-hw:.3f}" y="{cy-hh:.3f}" width="{w:.3f}" height="{h:.3f}" '
                    f'fill="none" stroke="white" stroke-width="0.12" '
                    f'stroke-dasharray="1,0.5" opacity="0.6"/>'
                )

                # ── Component body fill ───────────────────────────────────────
                svg.append(
                    f'<rect x="{cx-hw:.3f}" y="{cy-hh:.3f}" width="{w:.3f}" height="{h:.3f}" '
                    f'fill="{body_color}" stroke="{border_color}" stroke-width="{border_w:.2f}" rx="0.5"'
                    + (' filter="url(#glow)"' if is_drc_error else '') + '/>'
                )

                # ── Pin 1 corner chamfer ──────────────────────────────────────
                svg.append(
                    f'<polygon points="{cx-hw:.2f},{cy-hh:.2f} {cx-hw+1.8:.2f},{cy-hh:.2f} '
                    f'{cx-hw:.2f},{cy-hh+1.8:.2f}" fill="#daa520" fill-opacity="0.8"/>'
                )

                # ── Pads ──────────────────────────────────────────────────────
                if ctype in _MCU_TYPES or ctype in _LARGE_TYPES:
                    # SMD pads along left/right sides
                    n_pins = max(2, min(8, int(h / 2.5)))
                    pad_pitch = h / (n_pins + 1)
                    for side_x in [cx - hw, cx + hw]:
                        for i in range(1, n_pins + 1):
                            py_ = cy - hh + i * pad_pitch
                            svg.append(
                                f'<rect x="{side_x-0.5:.3f}" y="{py_-0.7:.3f}" '
                                f'width="1.0" height="1.4" class="pad-smd" rx="0.2"/>'
                            )
                else:
                    # THT annular ring pads (copper ring + drill hole)
                    is_gnd_comp = any(
                        any(n.split(".")[0] == cid for n in net.get("nodes", []))
                        and "gnd" in net.get("name", "").lower()
                        for net in nets
                    )
                    pad_r_outer = 0.9
                    pad_r_inner = 0.4  # drill
                    pad_color   = "#b87333" if is_gnd_comp else "#daa520"
                    for px_, py_ in [(cx - w*0.3, cy), (cx + w*0.3, cy)]:
                        # Annular ring (filled circle)
                        svg.append(
                            f'<circle cx="{px_:.3f}" cy="{py_:.3f}" r="{pad_r_outer:.2f}" '
                            f'fill="{pad_color}" stroke="#111" stroke-width="0.1"/>'
                        )
                        # Drill hole
                        svg.append(
                            f'<circle cx="{px_:.3f}" cy="{py_:.3f}" r="{pad_r_inner:.2f}" '
                            f'fill="#0a1a0a"/>'
                        )

                # ── Silkscreen ref label ───────────────────────────────────────
                fs = max(1.2, min(2.5, w * 0.30))
                svg.append(
                    f'<text x="{cx:.3f}" y="{cy-hh-0.6:.3f}" '
                    f'font-size="{fs:.2f}" fill="white" text-anchor="middle" '
                    f'font-family="monospace" class="silkscreen">{cid}</text>'
                )

                # ── Component name on silkscreen ───────────────────────────────
                comp_name = (comp.get("name","") or "")[:10]
                if comp_name:
                    fs2 = max(0.9, min(1.8, w * 0.22))
                    svg.append(
                        f'<text x="{cx:.3f}" y="{cy+0.5:.3f}" '
                        f'font-size="{fs2:.2f}" fill="white" fill-opacity="0.7" '
                        f'text-anchor="middle" dominant-baseline="middle" '
                        f'font-family="monospace">{comp_name}</text>'
                    )

                # ── DRC error badge ───────────────────────────────────────────
                if is_drc_error:
                    svg.append(
                        f'<rect x="{cx+hw-3:.3f}" y="{cy-hh:.3f}" width="3" height="2.2" '
                        f'fill="#ff3333" rx="0.4"/>'
                    )
                    svg.append(
                        f'<text x="{cx+hw-1.5:.3f}" y="{cy-hh+1.6:.3f}" '
                        f'font-size="1.4" fill="white" text-anchor="middle" '
                        f'font-weight="bold">!</text>'
                    )

            # ── Legend ───────────────────────────────────────────────────────
            svg.append('<!-- Legend -->')
            legend_x = board_w - 38.0
            legend_y = 3.0
            svg.append(
                f'<rect x="{legend_x:.2f}" y="{legend_y:.2f}" width="36" height="18" '
                f'fill="#0d1a0d" fill-opacity="0.85" stroke="#336633" stroke-width="0.2" rx="1"/>'
            )
            legend_items = [
                ("#daa520", "Top copper (señales)"),
                ("#b87333", "Bottom copper (GND/VCC)"),
                ("#888888", "Vias"),
            ]
            for i, (color, label) in enumerate(legend_items):
                ly = legend_y + 3.5 + i * 4.5
                svg.append(f'<line x1="{legend_x+2:.2f}" y1="{ly:.2f}" x2="{legend_x+8:.2f}" y2="{ly:.2f}" '
                           f'stroke="{color}" stroke-width="1"/>')
                svg.append(f'<text x="{legend_x+10:.2f}" y="{ly+0.6:.2f}" font-size="2" '
                           f'fill="#88cc88" font-family="monospace">{label}</text>')

            # ── DRC summary strip ─────────────────────────────────────────────
            n_err = len(drc.get("errors", []))
            drc_color = "#ff4444" if n_err else "#44ff44"
            drc_text  = f"DRC: {n_err} error(es)" if n_err else "DRC: OK"
            svg.append(
                f'<rect x="1" y="{board_h-4:.2f}" width="30" height="3" '
                f'fill="{drc_color}" fill-opacity="0.2" rx="0.5"/>'
            )
            svg.append(
                f'<text x="2" y="{board_h-2:.2f}" font-size="1.8" fill="{drc_color}" '
                f'font-family="monospace">{drc_text}</text>'
            )

            # ── Board info ────────────────────────────────────────────────────
            svg.append(
                f'<text x="{board_w/2:.2f}" y="{board_h-0.8:.2f}" '
                f'font-size="1.4" fill="#88cc88" text-anchor="middle" font-family="monospace">'
                f'Stratum PCB · {circuit_data.get("name","")[:35]} · '
                f'{board_w:.0f}×{board_h:.0f}mm · {len(components)} comps</text>'
            )
            svg.append('</svg>')
            return "\n".join(svg)

        except Exception as e:
            logger.error(f"Error generando PCB SVG: {e}")
            return (f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="100">'
                    f'<text x="10" y="50" fill="red" font-size="12">Error: {e}</text></svg>')

    # ── Gerber RS-274X ────────────────────────────────────────────────────────

    def generate_gerber_files(self, circuit_data: Dict[str, Any]) -> Dict[str, str]:
        try:
            components = circuit_data.get("components", [])
            nets       = circuit_data.get("nets", [])
            board_w, board_h = _board_size(components)
            positions  = _place_components(components, board_w, board_h, nets)
            traces     = _route_traces(nets, positions)

            top_traces = [t for t in traces if t["layer"] == "top"]
            bot_traces = [t for t in traces if t["layer"] == "bottom"]

            return {
                "copper_top.gtl":      self._gerber_copper(top_traces, board_w, board_h, "Top Copper"),
                "copper_bottom.gbl":   self._gerber_copper(bot_traces, board_w, board_h, "Bottom Copper"),
                "silkscreen_top.gto":  self._gerber_silk(components, positions),
                "soldermask_top.gts":  self._gerber_soldermask(components, positions, board_w, board_h),
                "soldermask_bot.gbs":  self._gerber_soldermask(components, positions, board_w, board_h),
                "drills.xln":          self._gerber_drills(components, positions),
                "outline.gko":         self._gerber_outline(board_w, board_h),
                "README.txt":          self._gerber_readme(circuit_data, board_w, board_h),
            }
        except Exception as e:
            logger.error(f"Error generando Gerber: {e}")
            return {"error.log": f"Error generating Gerber: {e}"}

    # ── Gerber helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _hdr(layer_name: str) -> str:
        return (
            f"G04 Stratum PCB — {layer_name} *\n"
            "%FSLAX46Y46*%\n"
            "%MOMM*%\n"
            "%LPD*%\n"
            "G01*\n"
            "%ADD10C,0.200*%\n"   # aperture 10: 0.2mm circle
            "%ADD11C,0.500*%\n"   # aperture 11: 0.5mm circle (signal trace)
            "%ADD12C,1.200*%\n"   # aperture 12: 1.2mm circle (power trace)
            "%ADD13C,1.000*%\n"   # aperture 13: 1.0mm drill
            "D10*\n"
        )

    def _gerber_copper(self, traces: List[Dict], bw: float, bh: float, name: str) -> str:
        g = self._hdr(name)
        for tr in traces:
            ap = "D12" if tr["width"] > 0.8 else "D11"
            # convert mm to Gerber units (×10000 for FSLAX46Y46? Actually ×1000000 for X4Y4)
            # FSLAX46Y46 = format 4.6 → units are 0.000001mm per digit
            scale = 1_000_000  # for X4Y4 with FSLAX46Y46
            def g_coord(v: float) -> int:
                return int(round(v * 1_000_000))
            g += f"{ap}*\n"
            g += f"X{g_coord(tr['x1'])}Y{g_coord(tr['y1'])}D02*\n"
            g += f"X{g_coord(tr['x2'])}Y{g_coord(tr['y2'])}D01*\n"
        g += "M02*\n"
        return g

    def _gerber_silk(self, components: List[Dict],
                     positions: Dict[str, Tuple[float, float]]) -> str:
        g = self._hdr("Silkscreen Top")
        for comp in components:
            cid = comp["id"]
            if cid not in positions:
                continue
            cx, cy = positions[cid]
            ctype = comp.get("resolved_type", comp.get("type", "generic")).lower()
            w, h = _fp(ctype)
            # Component outline
            def gc(v: float) -> int:
                return int(round(v * 1_000_000))
            # Draw rectangle outline
            x1, y1 = cx - w/2, cy - h/2
            x2, y2 = cx + w/2, cy + h/2
            g += "D10*\n"
            g += f"X{gc(x1)}Y{gc(y1)}D02*\n"
            g += f"X{gc(x2)}Y{gc(y1)}D01*\n"
            g += f"X{gc(x2)}Y{gc(y2)}D01*\n"
            g += f"X{gc(x1)}Y{gc(y2)}D01*\n"
            g += f"X{gc(x1)}Y{gc(y1)}D01*\n"
        g += "M02*\n"
        return g

    def _gerber_soldermask(self, components: List[Dict],
                           positions: Dict[str, Tuple[float, float]],
                           bw: float, bh: float) -> str:
        g = self._hdr("Soldermask")
        # Clearance openings for each pad
        def gc(v: float) -> int:
            return int(round(v * 1_000_000))
        for comp in components:
            cid = comp["id"]
            if cid not in positions:
                continue
            cx, cy = positions[cid]
            ctype = comp.get("resolved_type", comp.get("type", "generic")).lower()
            w, h = _fp(ctype)
            if ctype in _MCU_TYPES:
                pads = [(cx - w/2, cy - h/2), (cx + w/2, cy - h/2),
                        (cx - w/2, cy + h/2), (cx + w/2, cy + h/2)]
                r = 1.0
            else:
                pads = [(cx - w/2, cy), (cx + w/2, cy)]
                r = 0.7
            g += f"%ADD20C,{r:.3f}*%\nD20*\n"
            for px, py in pads:
                g += f"X{gc(px)}Y{gc(py)}D03*\n"  # D03 = flash
        g += "M02*\n"
        return g

    def _gerber_drills(self, components: List[Dict],
                       positions: Dict[str, Tuple[float, float]]) -> str:
        lines = ["M48", "FMAT,2", "METRIC,LZ", "T1C0.8", "%", "T1"]
        for comp in components:
            cid = comp["id"]
            if cid not in positions:
                continue
            cx, cy = positions[cid]
            ctype = comp.get("resolved_type", comp.get("type", "generic")).lower()
            w, h = _fp(ctype)
            if ctype in _MCU_TYPES:
                pads = [(cx - w/2, cy - h/2), (cx + w/2, cy - h/2),
                        (cx - w/2, cy + h/2), (cx + w/2, cy + h/2)]
            else:
                pads = [(cx - w/2, cy), (cx + w/2, cy)]
            for px, py in pads:
                lines.append(f"X{px:.4f}Y{py:.4f}")
        lines.append("M30")
        return "\n".join(lines)

    def _gerber_outline(self, bw: float, bh: float) -> str:
        g = self._hdr("Board Outline")
        def gc(v: float) -> int:
            return int(round(v * 1_000_000))
        g += "D10*\n"
        g += f"X{gc(0)}Y{gc(0)}D02*\n"
        g += f"X{gc(bw)}Y{gc(0)}D01*\n"
        g += f"X{gc(bw)}Y{gc(bh)}D01*\n"
        g += f"X{gc(0)}Y{gc(bh)}D01*\n"
        g += f"X{gc(0)}Y{gc(0)}D01*\n"
        g += "M02*\n"
        return g

    def _gerber_readme(self, circuit_data: Dict, bw: float, bh: float) -> str:
        comps = circuit_data.get("components", [])
        return (
            f"Stratum PCB Export\n"
            f"==================\n"
            f"Circuit: {circuit_data.get('name','')}\n"
            f"Description: {circuit_data.get('description','')}\n"
            f"Power: {circuit_data.get('power','')}\n"
            f"Board size: {bw:.1f} × {bh:.1f} mm\n"
            f"Components: {len(comps)}\n"
            f"Layers: 2 (Top copper + Bottom copper)\n\n"
            f"Files:\n"
            f"  copper_top.gtl    — Top copper layer\n"
            f"  copper_bottom.gbl — Bottom copper layer\n"
            f"  silkscreen_top.gto — Silkscreen\n"
            f"  soldermask_top.gts — Top soldermask\n"
            f"  soldermask_bot.gbs — Bottom soldermask\n"
            f"  drills.xln        — Drill file (Excellon)\n"
            f"  outline.gko       — Board outline\n\n"
            f"Warnings:\n"
        ) + "\n".join(f"  - {w}" for w in circuit_data.get("warnings", []))


def _body_color(ctype: str) -> str:
    colors = {
        "resistor": "#d4a028", "capacitor": "#cccccc",
        "capacitor_electrolytic": "#202060",
        "led": "#446688", "led_rgb": "#664488",
        "diode": "#888888", "1n4007": "#888888", "1n5819": "#888888",
        "relay": "#224488", "relay_module": "#224488",
        "ssr": "#552222",
        "arduino_uno": "#006699", "arduino_mega": "#006699", "arduino_nano": "#006699",
        "esp32": "#aa2222", "esp8266": "#aa2222",
        "motor_driver": "#333333", "buzzer": "#222222",
        "oled": "#111133", "lcd": "#334422",
        # Industrial
        "transformer": "#3a2a18",
        "smps": "#444444",
        "bridge_rectifier": "#222222",
        "fuse": "#cccccc", "fuse_holder": "#cccccc",
        "varistor": "#cc6600", "mov": "#cc6600",
        "voltage_regulator": "#1a1a1a", "lm7805": "#1a1a1a",
        "lm317": "#1a1a1a", "ams1117": "#1a1a1a", "regulator": "#1a1a1a",
        "optoacoplador": "#222222", "pc817": "#222222",
        "inductor": "#332211", "inductor_cm": "#332211",
        "x_capacitor": "#aa6600",
        "connector": "#226633", "terminal_block": "#226633",
        "header": "#888888", "pin_header": "#888888",
    }
    return colors.get(ctype, "#3a3a3a")
