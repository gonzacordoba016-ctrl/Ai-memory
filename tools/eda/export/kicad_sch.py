"""
KiCad Schematic exporter — IR → .kicad_sch (S-expression v6+).

Emite:
    - Header (version, generator, paper)
    - lib_symbols con un símbolo custom inline por componente
    - symbol instances en sus posiciones (placement)
    - wires derivados de los nets (centroid + L-shape, mismo cálculo que
      el schematic renderer)
    - net labels en endpoints

Sin lógica de placement/routing — consume lo que el IR ya tiene.
"""
from __future__ import annotations

import hashlib

from tools.eda.component_registry import ComponentSpec, get_registry
from tools.eda.ir import Circuit, Component, Net, Vec2

from ._sexpr import fmt, quote, sexpr


_GENERATOR = "stratum_eda"
_VERSION = "20211123"


def export_kicad_sch(circuit: Circuit, *, title: str = "Schematic") -> str:
    """IR → texto del .kicad_sch."""
    registry = get_registry()
    lines: list[str] = []
    lines.append(f"(kicad_sch (version {_VERSION}) (generator {_GENERATOR})")
    lines.append(f"  (paper \"A4\")")
    lines.append(f"  (title_block (title {quote(title)}))")

    # lib_symbols — un símbolo custom por type único.
    types_used: list[str] = []
    seen: set[str] = set()
    for c in sorted(circuit.components, key=lambda c: c.ref):
        if c.type not in seen:
            types_used.append(c.type)
            seen.add(c.type)
    lines.append("  (lib_symbols")
    for t in types_used:
        spec = registry.get(t)
        lines.extend("    " + ln for ln in _lib_symbol(t, spec))
    lines.append("  )")

    # symbol instances.
    for c in sorted(circuit.components, key=lambda c: c.ref):
        if c.placement is None:
            continue
        lines.extend("  " + ln for ln in _symbol_instance(c))

    # Wires + net labels (centroid + L-shape, sort por nombre).
    pos_of: dict[str, Vec2] = {
        c.ref: c.placement.position for c in circuit.components
        if c.placement is not None
    }
    for net in sorted(circuit.nets, key=lambda n: n.name):
        pts = [pos_of[n.ref] for n in net.nodes if n.ref in pos_of]
        if len(pts) < 2:
            continue
        cx = round(sum(p.x for p in pts) / len(pts), 4)
        cy = round(sum(p.y for p in pts) / len(pts), 4)
        for p in pts:
            # H-then-V via centroid.
            if abs(p.x - cx) > 1e-6:
                lines.append(_wire(p.x, p.y, cx, p.y))
            if abs(p.y - cy) > 1e-6:
                lines.append(_wire(cx, p.y, cx, cy))
        # Net label en (cx, cy).
        lines.append(_net_label(net.name, cx, cy))

    lines.append(")")
    return "\n".join(lines)


# ────────────────────────────────────────────────────────────────────────────
# lib_symbols
# ────────────────────────────────────────────────────────────────────────────


def _lib_symbol(type_key: str, spec: ComponentSpec | None) -> list[str]:
    """Símbolo inline básico — caja con pines a izquierda/derecha."""
    sym_id = f"Stratum:{type_key}"
    if spec is None:
        pins: list[tuple[str, str]] = [("1", ""), ("2", "")]
        cat = "unknown"
    else:
        pins = [(p.number, p.name) for p in spec.pins]
        cat = spec.category

    box_w = max(6.0, len(pins) * 0.4 + 4.0)
    box_h = max(4.0, len(pins) * 1.0)
    out: list[str] = []
    out.append(f"(symbol {quote(sym_id)} (in_bom yes) (on_board yes)")
    out.append(f"  (property \"Reference\" \"{_default_ref_prefix(cat)}\" "
               f"(at 0 {fmt(box_h / 2 + 2)} 0))")
    out.append(f"  (property \"Value\" {quote(type_key)} (at 0 {fmt(-box_h / 2 - 2)} 0))")
    out.append(f"  (symbol \"{type_key}_0_1\"")
    out.append(f"    (rectangle (start {fmt(-box_w / 2)} {fmt(box_h / 2)}) "
               f"(end {fmt(box_w / 2)} {fmt(-box_h / 2)})"
               f" (stroke (width 0.254) (type default))"
               f" (fill (type background))"
               f")")
    out.append(f"  )")
    out.append(f"  (symbol \"{type_key}_1_1\"")
    half = len(pins) // 2 if len(pins) > 1 else 0
    left_pins = pins[:half] if half > 0 else []
    right_pins = pins[half:]
    spacing = box_h / (max(len(left_pins), len(right_pins), 1) + 1)
    for i, (num, name) in enumerate(left_pins):
        y = box_h / 2 - spacing * (i + 1)
        out.append(_pin_def(-box_w / 2 - 2.54, y, 0, num, name))
    for i, (num, name) in enumerate(right_pins):
        y = box_h / 2 - spacing * (i + 1)
        out.append(_pin_def(box_w / 2 + 2.54, y, 180, num, name))
    out.append(f"  )")
    out.append(f")")
    return out


def _pin_def(x: float, y: float, rot: int, number: str, name: str) -> str:
    return (f"    (pin passive line (at {fmt(x)} {fmt(y)} {rot}) "
            f"(length 2.54)"
            f" (name {quote(name or 'X')} (effects (font (size 1 1))))"
            f" (number {quote(number)} (effects (font (size 1 1)))))")


def _default_ref_prefix(category: str) -> str:
    return {
        "mcu":       "U",
        "ic":        "U",
        "sensor":    "S",
        "display":   "D",
        "power":     "U",
        "passive":   "X",
        "connector": "J",
        "unknown":   "X",
    }.get(category, "X")


# ────────────────────────────────────────────────────────────────────────────
# Symbol instances
# ────────────────────────────────────────────────────────────────────────────


def _symbol_instance(comp: Component) -> list[str]:
    pos = comp.placement.position
    rot = int(round(comp.placement.rotation_deg))
    sym_id = f"Stratum:{comp.type}"
    uid = _uuid_for(comp.ref)
    out = [
        f"(symbol (lib_id {quote(sym_id)}) "
        f"(at {fmt(pos.x)} {fmt(pos.y)} {rot}) (uuid {uid})",
        f"  (property \"Reference\" {quote(comp.ref)} "
        f"(at {fmt(pos.x)} {fmt(pos.y - 8)} 0))",
        f"  (property \"Value\" {quote(comp.value or comp.type)} "
        f"(at {fmt(pos.x)} {fmt(pos.y + 8)} 0))",
        f")",
    ]
    return out


# ────────────────────────────────────────────────────────────────────────────
# Wires + labels
# ────────────────────────────────────────────────────────────────────────────


def _wire(x1: float, y1: float, x2: float, y2: float) -> str:
    uid = _uuid_for(f"wire_{x1}_{y1}_{x2}_{y2}")
    return (f"  (wire (pts (xy {fmt(x1)} {fmt(y1)}) (xy {fmt(x2)} {fmt(y2)}))"
            f" (stroke (width 0.0)) (uuid {uid}))")


def _net_label(name: str, x: float, y: float) -> str:
    uid = _uuid_for(f"label_{name}")
    return (f"  (label {quote(name)} (at {fmt(x)} {fmt(y)} 0)"
            f" (effects (font (size 1.27 1.27))) (uuid {uid}))")


# ────────────────────────────────────────────────────────────────────────────
# UUIDs deterministas
# ────────────────────────────────────────────────────────────────────────────


def _uuid_for(seed: str) -> str:
    """UUID v4-shaped derivado del seed → output byte-determinista."""
    h = hashlib.sha256(seed.encode()).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"
