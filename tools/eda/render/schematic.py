"""
Schematic Renderer puro — consume Circuit IR con placement, dibuja SVG.

NO toma decisiones de:
    - placement (lo hace el placement engine)
    - routing/wire layout (geometría wire = derivación trivial de net.nodes)
    - net inference (los nets vienen del IR)
    - pin assignment (lo hace el pin allocator)

Las "wires" del esquemático son derivadas mecánicamente:
    - Para cada net, calcular centroide de las posiciones de sus nodos.
    - Cada nodo se conecta al centroide vía L-shape Manhattan.
    - Esto es cálculo geométrico determinista, no routing.

Estructura SVG resultante:

    <svg>
      <defs><style/></defs>
      <g id="frame">marco + title block</g>
      <g id="wires">paths por net</g>
      <g id="components">símbolos en placement positions</g>
      <g id="net-labels">etiquetas en endpoints</g>
    </svg>
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from tools.eda.component_registry import get_registry
from tools.eda.ir import Circuit, Component, Vec2

from .svg import (
    circle,
    defs,
    fmt_num,
    group,
    polyline,
    rect,
    style,
    svg_root,
    text,
)


_DEFAULT_BODY_SIZE_BY_CATEGORY: dict[str, tuple[float, float]] = {
    "mcu":       (30.0, 22.0),
    "sensor":    (18.0, 14.0),
    "display":   (27.0, 18.0),
    "ic":        (20.0, 12.0),
    "power":     (18.0, 12.0),
    "connector": (15.0, 10.0),
    "passive":   (10.0, 4.0),
    "unknown":   (12.0, 8.0),
}


class SchematicRenderOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    show_title_block: bool = True
    show_net_labels: bool = True
    title: str = "Schematic"
    margin_mm: float = 10.0


# ────────────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────────────


def render_schematic_svg(
    circuit: Circuit,
    options: SchematicRenderOptions | None = None,
) -> str:
    options = options or SchematicRenderOptions()
    registry = get_registry()

    # Tamaño del board: del IR, o estimado de las posiciones.
    if circuit.board is not None:
        w, h = circuit.board.width_mm, circuit.board.height_mm
    else:
        w, h = _estimate_size(circuit)

    body_pieces: list[str] = []

    # Estilos.
    body_pieces.append(defs(style(_CSS)))

    # Frame (marco + title block).
    if options.show_title_block:
        body_pieces.append(_frame_svg(w, h, options.title, len(circuit.components)))

    # Wires (derivadas mecánicamente de nets + placements).
    body_pieces.append(_wires_svg(circuit))

    # Componentes en orden alfabético — determinismo.
    body_pieces.append(_components_svg(circuit, registry))

    # Net labels.
    if options.show_net_labels:
        body_pieces.append(_net_labels_svg(circuit))

    return svg_root(w, h, "".join(body_pieces))


# ────────────────────────────────────────────────────────────────────────────
# Componentes
# ────────────────────────────────────────────────────────────────────────────


def _components_svg(circuit: Circuit, registry) -> str:
    pieces: list[str] = []
    for comp in sorted(circuit.components, key=lambda c: c.ref):
        if comp.placement is None:
            continue
        pieces.append(_component_symbol(comp, registry))
    return group("".join(pieces), id="components")


def _component_symbol(comp: Component, registry) -> str:
    pos = comp.placement.position
    spec = registry.get(comp.type)
    cat = spec.category if spec else "unknown"
    bw, bh = _DEFAULT_BODY_SIZE_BY_CATEGORY.get(
        cat, _DEFAULT_BODY_SIZE_BY_CATEGORY["unknown"]
    )
    x = pos.x - bw / 2
    y = pos.y - bh / 2
    body = rect(
        fmt_num(x), fmt_num(y), fmt_num(bw), fmt_num(bh),
        **{"class": "symbol-body"},
    )
    ref_label = text(
        fmt_num(pos.x), fmt_num(y - 1.5), comp.ref,
        **{"class": "ref-label", "text-anchor": "middle"},
    )
    type_label = text(
        fmt_num(pos.x), fmt_num(y + bh + 3.5),
        comp.value or comp.type,
        **{"class": "type-label", "text-anchor": "middle"},
    )
    return group(
        body + ref_label + type_label,
        **{"class": "component", "data-ref": comp.ref},
    )


# ────────────────────────────────────────────────────────────────────────────
# Wires
# ────────────────────────────────────────────────────────────────────────────


def _wires_svg(circuit: Circuit) -> str:
    """Para cada net, conecta cada nodo al centroide del net vía L-shape."""
    pos_of: dict[str, Vec2] = {}
    for c in circuit.components:
        if c.placement is not None:
            pos_of[c.ref] = c.placement.position

    pieces: list[str] = []
    junctions: list[tuple[float, float]] = []

    for net in sorted(circuit.nets, key=lambda n: n.name):
        node_positions = [pos_of[n.ref] for n in net.nodes if n.ref in pos_of]
        if len(node_positions) < 2:
            continue
        cx = sum(p.x for p in node_positions) / len(node_positions)
        cy = sum(p.y for p in node_positions) / len(node_positions)
        for p in node_positions:
            # L-shape: H-then-V (horizontal primero).
            path = [(p.x, p.y), (cx, p.y), (cx, cy)]
            pieces.append(polyline(
                [(round(x, 3), round(y, 3)) for x, y in path],
                **{"class": "wire", "data-net": net.name},
            ))
        if len(node_positions) >= 3:
            junctions.append((cx, cy))

    # Junctions (puntitos donde se cruzan ≥3 wires).
    for jx, jy in junctions:
        pieces.append(circle(
            fmt_num(jx), fmt_num(jy), "0.6",
            **{"class": "junction"},
        ))

    return group("".join(pieces), id="wires")


# ────────────────────────────────────────────────────────────────────────────
# Net labels
# ────────────────────────────────────────────────────────────────────────────


def _net_labels_svg(circuit: Circuit) -> str:
    pos_of: dict[str, Vec2] = {
        c.ref: c.placement.position
        for c in circuit.components
        if c.placement is not None
    }
    pieces: list[str] = []
    for net in sorted(circuit.nets, key=lambda n: n.name):
        positions = [pos_of[n.ref] for n in net.nodes if n.ref in pos_of]
        if not positions:
            continue
        # Una sola etiqueta por net, en el primer node (ordered).
        first = positions[0]
        pieces.append(text(
            fmt_num(first.x + 4), fmt_num(first.y - 2),
            net.name,
            **{"class": "net-label"},
        ))
    return group("".join(pieces), id="net-labels")


# ────────────────────────────────────────────────────────────────────────────
# Frame + title block
# ────────────────────────────────────────────────────────────────────────────


def _frame_svg(w: float, h: float, title: str, comp_count: int) -> str:
    margin = 5.0
    pieces = [rect(
        fmt_num(margin), fmt_num(margin),
        fmt_num(w - 2 * margin), fmt_num(h - 2 * margin),
        **{"class": "frame"},
    )]
    # Title block bottom-right.
    tb_w, tb_h = 80.0, 18.0
    tx = w - margin - tb_w
    ty = h - margin - tb_h
    pieces.append(rect(
        fmt_num(tx), fmt_num(ty),
        fmt_num(tb_w), fmt_num(tb_h),
        **{"class": "title-block"},
    ))
    pieces.append(text(
        fmt_num(tx + 2), fmt_num(ty + 6), f"TITLE: {title}",
        **{"class": "title-text"},
    ))
    pieces.append(text(
        fmt_num(tx + 2), fmt_num(ty + 12), f"COMPONENTS: {comp_count}",
        **{"class": "title-text"},
    ))
    return group("".join(pieces), id="frame")


def _estimate_size(circuit: Circuit) -> tuple[float, float]:
    if not circuit.components:
        return 100.0, 80.0
    xs, ys = [], []
    for c in circuit.components:
        if c.placement is not None:
            xs.append(c.placement.position.x)
            ys.append(c.placement.position.y)
    if not xs:
        return 100.0, 80.0
    return max(xs) + 30.0, max(ys) + 30.0


_CSS = """
.frame { fill: none; stroke: #444; stroke-width: 0.3; }
.title-block { fill: #fafafa; stroke: #444; stroke-width: 0.2; }
.title-text { font-family: monospace; font-size: 3px; fill: #222; }
.component .symbol-body { fill: #fff8e1; stroke: #5a4a00; stroke-width: 0.25; }
.ref-label { font-family: sans-serif; font-size: 2.5px; fill: #2a2a8a; font-weight: bold; }
.type-label { font-family: sans-serif; font-size: 2px; fill: #555; }
.wire { stroke: #1a5a1a; stroke-width: 0.25; fill: none; }
.junction { fill: #1a5a1a; stroke: none; }
.net-label { font-family: monospace; font-size: 2px; fill: #1a5a1a; }
"""
