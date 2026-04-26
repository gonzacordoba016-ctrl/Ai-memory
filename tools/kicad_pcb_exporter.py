# tools/kicad_pcb_exporter.py
#
# Generates valid KiCad v6 PCB files (.kicad_pcb) from the internal netlist format.
# Strategy: reuse pcb_renderer's placement + Manhattan routing, emit S-expressions
# with real KiCad footprint refs (Resistor_THT:R_Axial_..., Module:Arduino_Nano).
#
# Output is openable in KiCad pcbnew. Footprints render as bounding boxes when
# the actual library is missing — KiCad does not refuse to open the file in that
# case, it just shows a placeholder. To get real shapes the user must have the
# standard KiCad libraries installed (default install).

from __future__ import annotations

import uuid as _uuid
from typing import Any, Dict, List, Optional, Tuple

from tools.pcb_renderer import (
    _place_components,
    _route_traces,
    _board_size,
    _fp,
)
from tools.kicad_exporter import _TYPE_TO_FOOTPRINT


# ── Helpers ──────────────────────────────────────────────────────────────────

def _uid() -> str:
    return str(_uuid.uuid4())


def _fmt(v: float) -> str:
    return f"{v:.4f}"


def _comp_type(comp: Dict) -> str:
    return (comp.get("resolved_type") or comp.get("type") or "").lower()


def _footprint_ref(comp: Dict) -> str:
    """Real KiCad footprint ref. Falls back to a generic 2-pad SMD if unknown."""
    fp = (comp.get("footprint") or "").strip()
    if fp and ":" in fp:
        return fp
    t = _comp_type(comp)
    return _TYPE_TO_FOOTPRINT.get(t, "Package_TO_SOT_THT:TO-220-3_Vertical")


def _is_power_net(name: str) -> bool:
    n = name.lower()
    return any(k in n for k in ("vcc", "gnd", "5v", "3v3", "vin", "vdd", "ground"))


# ── Pad geometry per component type ──────────────────────────────────────────
# Pads are described as (pad_number, dx_mm, dy_mm) relative to footprint origin.
# Uses simple THT 2-pad layout for passives; multi-pin parts use a row.

def _pad_layout(comp: Dict) -> List[Tuple[str, float, float]]:
    t = _comp_type(comp)
    fp_w, fp_h = _fp(t)

    # Two-terminal passives — pads on left/right edges
    two_term = {
        "resistor", "resistencia", "capacitor", "capacitor_electrolytic",
        "led", "led_rgb", "diode", "1n4007", "1n5819", "zener", "fuse",
        "inductor", "varistor",
    }
    if t in two_term:
        return [("1", -fp_w / 2 + 1.27, 0.0), ("2", fp_w / 2 - 1.27, 0.0)]

    # 3-terminal devices (TO-220, TO-92)
    three_term = {"transistor", "mosfet", "mosfet_n", "voltage_regulator",
                  "lm7805", "lm317", "ams1117", "ds18b20"}
    if t in three_term:
        return [("1", -2.54, 0.0), ("2", 0.0, 0.0), ("3", 2.54, 0.0)]

    # Push-button / switch
    if t in ("button", "switch"):
        return [("1", -2.54, -2.54), ("2", 2.54, -2.54),
                ("3", -2.54, 2.54), ("4", 2.54, 2.54)]

    # Bridge rectifier — 4 pads in a square
    if t == "bridge_rectifier":
        return [("1", -fp_w / 2 + 1.0, -fp_h / 2 + 1.0),
                ("2", fp_w / 2 - 1.0,  -fp_h / 2 + 1.0),
                ("3", -fp_w / 2 + 1.0, fp_h / 2 - 1.0),
                ("4", fp_w / 2 - 1.0,  fp_h / 2 - 1.0)]

    # Default — row of pads along bottom edge based on declared pins
    pin_names = comp.get("pins") or []
    n = max(len(pin_names), 4)
    pitch = min(2.54, max(1.0, (fp_w - 2.54) / max(n - 1, 1)))
    start = -(n - 1) * pitch / 2
    return [(str(i + 1), start + i * pitch, fp_h / 2 - 1.27) for i in range(n)]


def _resolve_pad(comp: Dict, pin_label: str) -> Optional[str]:
    """Map a circuit pin name (e.g. 'A', 'GND', '7') to a physical pad number."""
    pads = _pad_layout(comp)
    pad_numbers = [p[0] for p in pads]

    if pin_label in pad_numbers:
        return pin_label
    # Common aliases for 2-terminal devices
    aliases = {"A": "1", "K": "2", "+": "1", "-": "2"}
    if pin_label in aliases and aliases[pin_label] in pad_numbers:
        return aliases[pin_label]
    # Numeric pin → use modulo if MCU has many declared pins
    if pin_label.isdigit() and pad_numbers:
        idx = (int(pin_label) - 1) % len(pad_numbers)
        return pad_numbers[idx]
    return pad_numbers[0] if pad_numbers else None


# ── Net index ────────────────────────────────────────────────────────────────

def _build_net_index(nets: List[Dict]) -> Dict[str, int]:
    """Return {net_name: int_id}. Net 0 reserved for 'no net' per KiCad convention."""
    idx = {}
    for i, n in enumerate(nets, start=1):
        idx[n.get("name", f"NET{i}")] = i
    return idx


def _node_to_net(nets: List[Dict]) -> Dict[str, str]:
    """Return {'<comp_id>.<pin>': net_name}."""
    out = {}
    for n in nets:
        for node in n.get("nodes", []):
            out[node] = n.get("name", "")
    return out


# ── PCB header / sections ────────────────────────────────────────────────────

def _section_general(board_w: float, board_h: float) -> str:
    return (
        '  (general\n'
        '    (thickness 1.6)\n'
        '  )\n'
    )


def _section_paper() -> str:
    return '  (paper "A4")\n'


def _section_layers() -> str:
    return (
        '  (layers\n'
        '    (0 "F.Cu" signal)\n'
        '    (31 "B.Cu" signal)\n'
        '    (32 "B.Adhes" user "B.Adhesive")\n'
        '    (33 "F.Adhes" user "F.Adhesive")\n'
        '    (34 "B.Paste" user)\n'
        '    (35 "F.Paste" user)\n'
        '    (36 "B.SilkS" user "B.Silkscreen")\n'
        '    (37 "F.SilkS" user "F.Silkscreen")\n'
        '    (38 "B.Mask" user)\n'
        '    (39 "F.Mask" user)\n'
        '    (40 "Dwgs.User" user "User.Drawings")\n'
        '    (41 "Cmts.User" user "User.Comments")\n'
        '    (44 "Edge.Cuts" user)\n'
        '    (45 "Margin" user)\n'
        '    (46 "B.CrtYd" user "B.Courtyard")\n'
        '    (47 "F.CrtYd" user "F.Courtyard")\n'
        '    (48 "B.Fab" user)\n'
        '    (49 "F.Fab" user)\n'
        '  )\n'
    )


def _section_setup() -> str:
    return (
        '  (setup\n'
        '    (pad_to_mask_clearance 0)\n'
        '    (pcbplotparams\n'
        '      (layerselection 0x00010fc_ffffffff)\n'
        '      (disableapertmacros false)\n'
        '      (usegerberextensions false)\n'
        '      (usegerberattributes true)\n'
        '      (usegerberadvancedattributes true)\n'
        '      (creategerberjobfile true)\n'
        '      (svguseinch false)\n'
        '      (svgprecision 6)\n'
        '      (excludeedgelayer true)\n'
        '      (plotframeref false)\n'
        '      (viasonmask false)\n'
        '      (mode 1)\n'
        '      (useauxorigin false)\n'
        '      (hpglpennumber 1)\n'
        '      (hpglpenspeed 20)\n'
        '      (hpglpendiameter 15.000000)\n'
        '      (dxfpolygonmode true)\n'
        '      (dxfimperialunits true)\n'
        '      (dxfusepcbnewfont true)\n'
        '      (psnegative false)\n'
        '      (psa4output false)\n'
        '      (plotreference true)\n'
        '      (plotvalue true)\n'
        '      (plotinvisibletext false)\n'
        '      (sketchpadsonfab false)\n'
        '      (subtractmaskfromsilk false)\n'
        '      (outputformat 1)\n'
        '      (mirror false)\n'
        '      (drillshape 1)\n'
        '      (scaleselection 1)\n'
        '      (outputdirectory "")\n'
        '    )\n'
        '  )\n'
    )


def _section_nets(nets: List[Dict], net_index: Dict[str, int]) -> str:
    out = ['  (net 0 "")']
    for n in nets:
        nm = n.get("name", "")
        out.append(f'  (net {net_index[nm]} "{nm}")')
    return "\n".join(out) + "\n"


# ── Footprint S-expression ───────────────────────────────────────────────────

def _emit_footprint(comp: Dict,
                    pos: Tuple[float, float],
                    node_to_net: Dict[str, str],
                    net_index: Dict[str, int]) -> str:
    cx, cy = pos
    fp_ref = _footprint_ref(comp)
    cid    = comp.get("id", "U?")
    val    = comp.get("value") or comp.get("name") or _comp_type(comp)
    val    = str(val) + (comp.get("unit") or "")
    pads   = _pad_layout(comp)

    # Pin → pad number map for this comp, derived from incoming nets
    pin_to_pad: Dict[str, str] = {}
    for node, net_name in node_to_net.items():
        ps = node.split(".", 1)
        if len(ps) != 2 or ps[0] != cid:
            continue
        pad = _resolve_pad(comp, ps[1])
        if pad:
            pin_to_pad[ps[1]] = pad

    # Build inverse: pad_num → net_name (first-wins if multiple pins map to same pad)
    pad_net: Dict[str, str] = {}
    for pin, pad in pin_to_pad.items():
        net_for_pin = next(
            (nn for node, nn in node_to_net.items()
             if node.split(".", 1) == [cid, pin]),
            None,
        )
        if net_for_pin and pad not in pad_net:
            pad_net[pad] = net_for_pin

    lines = [
        f'  (footprint "{fp_ref}" (layer "F.Cu") (tedit 0)',
        f'    (at {_fmt(cx)} {_fmt(cy)})',
        f'    (descr "Stratum auto-placed")',
        f'    (tags "{_comp_type(comp)}")',
        f'    (path "/{_uid()}")',
        f'    (fp_text reference "{cid}" (at 0 -3.5) (layer "F.SilkS")',
        f'      (effects (font (size 1 1) (thickness 0.15)))',
        f'      (tstamp {_uid()})',
        f'    )',
        f'    (fp_text value "{val}" (at 0 3.5) (layer "F.Fab")',
        f'      (effects (font (size 1 1) (thickness 0.15)))',
        f'      (tstamp {_uid()})',
        f'    )',
    ]

    for pad_num, dx, dy in pads:
        net_name = pad_net.get(pad_num)
        net_part = ""
        if net_name and net_name in net_index:
            net_part = f' (net {net_index[net_name]} "{net_name}")'
        lines.append(
            f'    (pad "{pad_num}" thru_hole circle (at {_fmt(dx)} {_fmt(dy)}) '
            f'(size 1.7 1.7) (drill 0.8) (layers "*.Cu" "*.Mask"){net_part} '
            f'(tstamp {_uid()}))'
        )

    lines.append('  )')
    return "\n".join(lines) + "\n"


# ── Track segment S-expression ───────────────────────────────────────────────

def _emit_segment(seg: Dict, net_index: Dict[str, int]) -> str:
    layer = "B.Cu" if seg.get("layer") == "bottom" else "F.Cu"
    nid   = net_index.get(seg.get("net", ""), 0)
    return (
        f'  (segment (start {_fmt(seg["x1"])} {_fmt(seg["y1"])}) '
        f'(end {_fmt(seg["x2"])} {_fmt(seg["y2"])}) '
        f'(width {_fmt(seg.get("width", 0.5))}) '
        f'(layer "{layer}") (net {nid}) (tstamp {_uid()}))\n'
    )


def _emit_edge_cuts(board_w: float, board_h: float) -> str:
    """Rectangle outline on Edge.Cuts."""
    pts = [(0, 0), (board_w, 0), (board_w, board_h), (0, board_h), (0, 0)]
    out = []
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        out.append(
            f'  (gr_line (start {_fmt(x1)} {_fmt(y1)}) (end {_fmt(x2)} {_fmt(y2)}) '
            f'(stroke (width 0.05) (type default)) (layer "Edge.Cuts") '
            f'(tstamp {_uid()}))'
        )
    return "\n".join(out) + "\n"


# ── Public API ───────────────────────────────────────────────────────────────

def export_kicad_pcb(circuit_data: Dict[str, Any]) -> str:
    """Generate a KiCad v6 .kicad_pcb string from a Stratum circuit dict."""
    components = circuit_data.get("components", [])
    nets       = circuit_data.get("nets", [])

    if not components:
        return '(kicad_pcb (version 20211014) (generator stratum_v4))\n'

    bw, bh    = _board_size(components)
    positions = _place_components(components, bw, bh, nets=nets)
    traces    = _route_traces(nets, positions)
    net_index = _build_net_index(nets)
    n2n       = _node_to_net(nets)

    out = ['(kicad_pcb (version 20211014) (generator stratum_v4)']
    out.append(_section_general(bw, bh))
    out.append(_section_paper())
    out.append(_section_layers())
    out.append(_section_setup())
    out.append(_section_nets(nets, net_index))
    out.append(_emit_edge_cuts(bw, bh))

    for comp in components:
        if comp["id"] not in positions:
            continue
        out.append(_emit_footprint(comp, positions[comp["id"]], n2n, net_index))

    for seg in traces:
        out.append(_emit_segment(seg, net_index))

    out.append(')')
    return "".join(out)
