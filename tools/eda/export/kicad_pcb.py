"""
KiCad PCB exporter — IR → .kicad_pcb (S-expression v6+).

Emite:
    - Header (version, generator, paper, layers, setup)
    - Net table (1 entry por net)
    - Footprints en sus posiciones (placement) — body + 2 pads simples
    - Segmentos (traces) por net + layer
    - Vías
    - Edge.Cuts del board outline

Pads simples en el centro del componente — sin geometría real de footprint
(el legacy `kicad_pcb_exporter.py` la tiene; acá lo dejamos para una
iteración futura).
"""
from __future__ import annotations

import hashlib

from tools.eda.component_registry import get_registry
from tools.eda.ir import Circuit, Component, Layer

from ._sexpr import fmt, quote


_GENERATOR = "stratum_eda"
_VERSION = "20221018"


def export_kicad_pcb(circuit: Circuit) -> str:
    if circuit.board is None:
        raise ValueError(
            "kicad_pcb exporter requiere circuit.board (corré place primero)."
        )
    registry = get_registry()
    w = circuit.board.width_mm
    h = circuit.board.height_mm

    lines: list[str] = []
    lines.append(f"(kicad_pcb (version {_VERSION}) (generator {_GENERATOR})")
    lines.append("  (general (thickness 1.6))")
    lines.append("  (paper \"A4\")")
    lines.append("  (layers")
    for ly in (
        '(0 "F.Cu" signal)',
        '(31 "B.Cu" signal)',
        '(32 "B.Adhes" user)',
        '(33 "F.Adhes" user)',
        '(34 "B.Paste" user)',
        '(35 "F.Paste" user)',
        '(36 "B.SilkS" user)',
        '(37 "F.SilkS" user)',
        '(38 "B.Mask" user)',
        '(39 "F.Mask" user)',
        '(40 "Dwgs.User" user)',
        '(41 "Cmts.User" user)',
        '(44 "Edge.Cuts" user)',
    ):
        lines.append(f"    {ly}")
    lines.append("  )")
    lines.append('  (setup (pad_to_mask_clearance 0))')

    # Net table — index alfabético, con "" en index 0.
    sorted_nets = sorted({n.name for n in circuit.nets})
    net_index: dict[str, int] = {"": 0}
    lines.append('  (net 0 "")')
    for i, name in enumerate(sorted_nets, start=1):
        net_index[name] = i
        lines.append(f"  (net {i} {quote(name)})")

    # Footprints.
    pos_to_pads: dict[str, list[tuple[float, float, str]]] = {}
    for c in sorted(circuit.components, key=lambda c: c.ref):
        if c.placement is None:
            continue
        spec = registry.get(c.type)
        fp_id = (spec.footprint_full_id if spec
                 else "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical")
        is_smd = spec.smd if spec else False
        lines.extend(_footprint_lines(c, fp_id, is_smd, net_index))
        # Posición del componente como pad center (para que segments
        # próximos formen connectivity).
        p = c.placement.position
        pos_to_pads[c.ref] = [(p.x, p.y, "1")]

    # Segmentos (traces).
    for t in sorted(circuit.traces, key=lambda t: (t.layer.value, t.net)):
        net_idx = net_index.get(t.net, 0)
        layer_str = t.layer.value
        for i in range(len(t.points) - 1):
            a = t.points[i]
            b = t.points[i + 1]
            uid = _uuid_for(f"seg_{t.net}_{a.x}_{a.y}_{b.x}_{b.y}")
            lines.append(
                f"  (segment (start {fmt(a.x)} {fmt(a.y)}) "
                f"(end {fmt(b.x)} {fmt(b.y)}) "
                f"(width {fmt(t.width_mm)}) (layer {quote(layer_str)}) "
                f"(net {net_idx}) (tstamp {uid}))"
            )

    # Vías.
    for v in sorted(circuit.vias, key=lambda v: (v.net, v.position.x, v.position.y)):
        net_idx = net_index.get(v.net, 0)
        uid = _uuid_for(f"via_{v.net}_{v.position.x}_{v.position.y}")
        lines.append(
            f"  (via (at {fmt(v.position.x)} {fmt(v.position.y)}) "
            f"(size {fmt(v.diameter_mm)}) (drill {fmt(v.drill_mm)}) "
            f"(layers \"F.Cu\" \"B.Cu\") (net {net_idx}) (tstamp {uid}))"
        )

    # Edge.Cuts (rectángulo del board).
    for x1, y1, x2, y2 in (
        (0, 0, w, 0),
        (w, 0, w, h),
        (w, h, 0, h),
        (0, h, 0, 0),
    ):
        lines.append(
            f"  (gr_line (start {fmt(x1)} {fmt(y1)}) "
            f"(end {fmt(x2)} {fmt(y2)}) (layer \"Edge.Cuts\") (width 0.05))"
        )

    lines.append(")")
    return "\n".join(lines)


# ────────────────────────────────────────────────────────────────────────────
# Footprint emission
# ────────────────────────────────────────────────────────────────────────────


def _footprint_lines(
    comp: Component,
    fp_id: str,
    is_smd: bool,
    net_index: dict[str, int],
) -> list[str]:
    pos = comp.placement.position
    rot = int(round(comp.placement.rotation_deg))
    uid = _uuid_for(f"fp_{comp.ref}")
    lines: list[str] = []
    lines.append(
        f"  (footprint {quote(fp_id)} (layer \"F.Cu\") (tstamp {uid})"
    )
    lines.append(
        f"    (at {fmt(pos.x)} {fmt(pos.y)} {rot})"
    )
    lines.append(
        f"    (fp_text reference {quote(comp.ref)} "
        f"(at 0 -2 {rot}) (layer \"F.SilkS\") "
        f"(effects (font (size 1 1) (thickness 0.15))))"
    )
    lines.append(
        f"    (fp_text value {quote(comp.value or comp.type)} "
        f"(at 0 2 {rot}) (layer \"F.Fab\") "
        f"(effects (font (size 1 1) (thickness 0.15))))"
    )
    # Pads simples — dos pads contiguos al centro del componente.
    pad_kind = "smd" if is_smd else "thru_hole"
    pad_shape = "roundrect" if is_smd else "circle"
    pad_size = "1.5 1.0" if is_smd else "1.7 1.7"
    drill_clause = "" if is_smd else " (drill 0.8)"
    layers_clause = ('"F.Cu" "F.Paste" "F.Mask"' if is_smd
                     else '"*.Cu" "*.Mask"')
    for i, dx in enumerate([-1.27, 1.27], start=1):
        lines.append(
            f"    (pad \"{i}\" {pad_kind} {pad_shape} (at {fmt(dx)} 0) "
            f"(size {pad_size}){drill_clause} (layers {layers_clause}))"
        )
    lines.append("  )")
    return lines


# ────────────────────────────────────────────────────────────────────────────
# UUIDs deterministas
# ────────────────────────────────────────────────────────────────────────────


def _uuid_for(seed: str) -> str:
    h = hashlib.sha256(seed.encode()).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"
