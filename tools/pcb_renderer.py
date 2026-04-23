# tools/pcb_renderer.py
# PCB layout renderer: SVG visual preview + Gerber RS-274X for fabrication.
# Placement algorithm: group components by function, route traces with simple
# Manhattan segments. Not a full autorouter — gives a meaningful starting point.

from typing import Dict, Any, List, Tuple
from core.logger import get_logger

logger = get_logger(__name__)

# mm → px at 96 DPI
_MM2PX = 3.7795275591

# Functional groups for placement
_MCU_TYPES   = {"arduino_uno", "arduino_nano", "arduino_mega", "esp32", "esp8266",
                "stm32", "rp2040", "pico", "attiny", "mcu"}
_SMALL_TYPES = {"resistor", "capacitor", "diode", "led", "led_rgb", "1n4007", "1n5819"}
_LARGE_TYPES = {"relay", "relay_module", "motor_driver", "l298n", "drv8825",
                "display", "oled", "lcd", "battery"}

# Footprint dimensions in mm (W × H)
_FOOTPRINT: Dict[str, Tuple[float, float]] = {
    "resistor":     (6.5, 2.5),
    "capacitor":    (3.0, 3.0),
    "led":          (5.0, 5.0),
    "led_rgb":      (5.0, 5.0),
    "diode":        (6.5, 2.5),
    "1n4007":       (6.5, 2.5),
    "button":       (6.0, 6.0),
    "relay":        (19.0, 15.5),
    "relay_module": (19.0, 15.5),
    "motor_driver": (35.0, 35.0),
    "buzzer":       (12.0, 12.0),
    "oled":         (27.0, 27.0),
    "lcd":          (80.0, 36.0),
    "arduino_uno":  (68.6, 53.4),
    "arduino_nano": (18.0, 43.2),
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


# ──────────────────────────────────────────────────────────────────────────────
# Placement
# ──────────────────────────────────────────────────────────────────────────────

def _place_components(components: List[Dict],
                      board_w: float, board_h: float) -> Dict[str, Tuple[float, float]]:
    """
    Returns {comp_id: (cx_mm, cy_mm)} — component centers in mm.
    Layout:
      - MCU: center
      - Small passives: cluster near MCU
      - Large modules: outer rows
      - Misc: bottom row
    """
    positions: Dict[str, Tuple[float, float]] = {}

    groups: Dict[str, List[Dict]] = {g: [] for g in ("mcu", "small", "large", "misc")}
    for comp in components:
        t = comp.get("resolved_type", comp.get("type", "generic")).lower()
        groups[_group(t)].append(comp)

    margin = 5.0
    cx, cy = board_w / 2, board_h / 2

    # MCU(s) at center
    for i, comp in enumerate(groups["mcu"]):
        w, h = _fp(comp.get("resolved_type", comp.get("type", "generic")))
        positions[comp["id"]] = (cx + i * (w + 5.0), cy)

    # Small passives: grid below and right of MCU
    sx, sy = cx + 35.0, cy - 25.0
    sp = 8.0
    cols = 5
    for i, comp in enumerate(groups["small"]):
        col, row = i % cols, i // cols
        positions[comp["id"]] = (sx + col * sp, sy + row * sp)

    # Large modules: left column
    lx, ly = margin + 20.0, margin + 20.0
    for i, comp in enumerate(groups["large"]):
        w, h = _fp(comp.get("resolved_type", comp.get("type", "generic")))
        positions[comp["id"]] = (lx, ly + i * (h + 6.0))

    # Misc: bottom row
    bx, by = margin + 15.0, board_h - margin - 10.0
    for i, comp in enumerate(groups["misc"]):
        positions[comp["id"]] = (bx + i * 14.0, by)

    return positions


# ──────────────────────────────────────────────────────────────────────────────
# Board dimensions
# ──────────────────────────────────────────────────────────────────────────────

def _board_size(components: List[Dict]) -> Tuple[float, float]:
    n = len(components)
    has_mcu  = any(c.get("resolved_type", c.get("type", "")).lower() in _MCU_TYPES
                   for c in components)
    has_large = any(c.get("resolved_type", c.get("type", "")).lower() in _LARGE_TYPES
                    for c in components)
    base_w = max(50.0, n * 8.0 + 30.0)
    base_h = max(40.0, n * 6.0 + 20.0)
    if has_mcu:
        base_w = max(base_w, 90.0)
        base_h = max(base_h, 70.0)
    if has_large:
        base_w = max(base_w, 120.0)
        base_h = max(base_h, 90.0)
    return (min(base_w, 200.0), min(base_h, 160.0))


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
            positions  = _place_components(components, board_w, board_h)
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
                border_w     = 0.5 if is_drc_error else 0.25

                # Component body
                svg.append(
                    f'<rect x="{cx-hw:.3f}" y="{cy-hh:.3f}" width="{w:.3f}" height="{h:.3f}" '
                    f'fill="{body_color}" stroke="{border_color}" stroke-width="{border_w:.2f}" rx="0.5"'
                    + (' filter="url(#glow)"' if is_drc_error else '') + '/>'
                )

                # Pin 1 corner chamfer
                svg.append(
                    f'<polygon points="{cx-hw:.2f},{cy-hh:.2f} {cx-hw+1.5:.2f},{cy-hh:.2f} '
                    f'{cx-hw:.2f},{cy-hh+1.5:.2f}" fill="#daa520" fill-opacity="0.7"/>'
                )

                # Pads — rectangular for ICs/modules, oval for passives
                if ctype in _MCU_TYPES or ctype in _LARGE_TYPES:
                    # Multiple pads along sides
                    n_pins = max(2, min(6, int(w / 3)))
                    for side, (px_base, py_base, dxs, dys) in enumerate([
                        (cx - hw, cy - hh + 1.5, 0, h / (n_pins + 1)),    # left
                        (cx + hw, cy - hh + 1.5, 0, h / (n_pins + 1)),    # right
                    ]):
                        for i in range(1, n_pins + 1):
                            px_ = px_base
                            py_ = py_base + (i - 1) * dys
                            svg.append(
                                f'<rect x="{px_-0.4:.3f}" y="{py_-0.6:.3f}" '
                                f'width="0.8" height="1.2" class="pad-smd" rx="0.2"/>'
                            )
                else:
                    # Two circular THT pads
                    is_gnd_comp = any(
                        cid in n.get("nodes", [f"{cid}.x"])[0] and
                        ("gnd" in n.get("name", "").lower())
                        for n in nets
                    )
                    pad_cls = "pad-gnd" if is_gnd_comp else "pad"
                    for px_, py_ in [(cx - hw, cy), (cx + hw, cy)]:
                        svg.append(f'<circle cx="{px_:.3f}" cy="{py_:.3f}" r="0.7" class="{pad_cls}"/>')
                        svg.append(f'<circle cx="{px_:.3f}" cy="{py_:.3f}" r="0.35" fill="#111"/>')

                # Silkscreen ref label
                fs = max(1.0, min(2.2, w * 0.28))
                svg.append(
                    f'<text x="{cx:.3f}" y="{cy+0.4:.3f}" '
                    f'font-size="{fs:.2f}" fill="white" text-anchor="middle" '
                    f'dominant-baseline="middle" class="silkscreen">{cid}</text>'
                )

                # DRC error badge
                if is_drc_error:
                    svg.append(
                        f'<rect x="{cx+hw-3:.3f}" y="{cy-hh:.3f}" width="3" height="2" '
                        f'fill="#ff3333" rx="0.3"/>'
                    )
                    svg.append(
                        f'<text x="{cx+hw-1.5:.3f}" y="{cy-hh+1.5:.3f}" '
                        f'font-size="1.2" fill="white" text-anchor="middle">!</text>'
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
            positions  = _place_components(components, board_w, board_h)
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
        "resistor": "#d4a028", "capacitor": "#cccccc", "led": "#446688",
        "led_rgb": "#664488", "diode": "#888888", "relay": "#224488",
        "relay_module": "#224488", "arduino_uno": "#006699", "esp32": "#aa2222",
        "esp8266": "#aa2222", "motor_driver": "#333333", "buzzer": "#222222",
        "oled": "#111133", "lcd": "#334422",
    }
    return colors.get(ctype, "#3a3a3a")
