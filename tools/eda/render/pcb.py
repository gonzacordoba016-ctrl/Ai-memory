"""
PCB Renderer puro — consume Circuit IR con placement + traces + vias,
emite SVG.

NO toma decisiones de:
    - placement (asumido en Component.placement)
    - routing (asumido en Circuit.traces)
    - via insertion (asumido en Circuit.vias)
    - footprint selection (toma footprint_full_id del registry)

Solo dibuja:
    - Edge cuts (rectángulo del board)
    - Footprints en su placement (cuerpo + courtyard + ref + value)
    - Traces como polylines en su layer (color por capa)
    - Vías como círculos
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from tools.eda.component_registry import get_registry
from tools.eda.ir import Circuit, Component, Layer, Trace, Vec2, Via

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


_DEFAULT_FP_SIZE_BY_CATEGORY: dict[str, tuple[float, float]] = {
    "mcu":       (30.0, 22.0),
    "sensor":    (18.0, 14.0),
    "display":   (27.0, 27.0),
    "ic":        (20.0, 12.0),
    "power":     (10.4, 8.7),
    "connector": (15.0, 10.0),
    "passive":   (8.0,  4.0),
    "unknown":   (12.0, 8.0),
}


class PCBRenderOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    show_edge_cuts: bool = True
    show_silkscreen: bool = True
    show_courtyards: bool = True
    background_dark: bool = True


# ────────────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────────────


def render_pcb_svg(
    circuit: Circuit,
    options: PCBRenderOptions | None = None,
) -> str:
    options = options or PCBRenderOptions()
    registry = get_registry()

    if circuit.board is None:
        # Si no vino del placement engine, no rendereamos.
        raise ValueError("PCB renderer requiere circuit.board (corré el "
                         "placement engine antes).")

    w, h = circuit.board.width_mm, circuit.board.height_mm

    body_pieces: list[str] = []

    # Estilos.
    body_pieces.append(defs(style(_CSS_DARK if options.background_dark
                                  else _CSS_LIGHT)))

    # Background.
    body_pieces.append(rect(0, 0, fmt_num(w), fmt_num(h),
                            **{"class": "pcb-bg"}))

    # Edge cuts.
    if options.show_edge_cuts:
        body_pieces.append(_edge_cuts_svg(w, h))

    # Copper layer B.Cu primero (debajo).
    body_pieces.append(_traces_svg(circuit.traces, Layer.B_CU))
    body_pieces.append(_traces_svg(circuit.traces, Layer.F_CU))

    # Vías por encima del copper.
    body_pieces.append(_vias_svg(circuit.vias))

    # Footprints (silk arriba de todo).
    body_pieces.append(_footprints_svg(circuit, registry, options))

    return svg_root(w, h, "".join(body_pieces))


# ────────────────────────────────────────────────────────────────────────────
# Edge cuts
# ────────────────────────────────────────────────────────────────────────────


def _edge_cuts_svg(w: float, h: float) -> str:
    margin = 0.5
    return group(
        rect(
            fmt_num(margin), fmt_num(margin),
            fmt_num(w - 2 * margin), fmt_num(h - 2 * margin),
            **{"class": "edge-cuts"},
        ),
        id="edge-cuts",
    )


# ────────────────────────────────────────────────────────────────────────────
# Traces
# ────────────────────────────────────────────────────────────────────────────


def _traces_svg(traces: list[Trace], layer: Layer) -> str:
    pieces: list[str] = []
    layer_class = "layer-f-cu" if layer == Layer.F_CU else "layer-b-cu"
    for t in sorted(traces, key=lambda t: (t.layer.value, t.net)):
        if t.layer != layer:
            continue
        points = [(round(p.x, 3), round(p.y, 3)) for p in t.points]
        pieces.append(polyline(
            points,
            **{
                "class": f"trace {layer_class}",
                "data-net": t.net,
                "stroke-width": fmt_num(t.width_mm),
                "stroke-linecap": "round",
                "stroke-linejoin": "round",
            },
        ))
    return group("".join(pieces), id=f"copper-{layer.value.lower().replace('.', '-')}")


# ────────────────────────────────────────────────────────────────────────────
# Vías
# ────────────────────────────────────────────────────────────────────────────


def _vias_svg(vias: list[Via]) -> str:
    pieces: list[str] = []
    for v in sorted(vias, key=lambda v: (v.net, v.position.x, v.position.y)):
        pieces.append(circle(
            fmt_num(v.position.x), fmt_num(v.position.y),
            fmt_num(v.diameter_mm / 2),
            **{"class": "via", "data-net": v.net},
        ))
        # Drill hole en el centro.
        pieces.append(circle(
            fmt_num(v.position.x), fmt_num(v.position.y),
            fmt_num(v.drill_mm / 2),
            **{"class": "via-drill"},
        ))
    return group("".join(pieces), id="vias")


# ────────────────────────────────────────────────────────────────────────────
# Footprints
# ────────────────────────────────────────────────────────────────────────────


def _footprints_svg(circuit: Circuit, registry,
                     options: PCBRenderOptions) -> str:
    pieces: list[str] = []
    for comp in sorted(circuit.components, key=lambda c: c.ref):
        if comp.placement is None:
            continue
        pieces.append(_footprint(comp, registry, options))
    return group("".join(pieces), id="footprints")


def _footprint(comp: Component, registry,
                options: PCBRenderOptions) -> str:
    pos = comp.placement.position
    spec = registry.get(comp.type)
    cat = spec.category if spec else "unknown"
    fw, fh = _DEFAULT_FP_SIZE_BY_CATEGORY.get(
        cat, _DEFAULT_FP_SIZE_BY_CATEGORY["unknown"]
    )
    x = pos.x - fw / 2
    y = pos.y - fh / 2

    pieces: list[str] = []

    # Courtyard (boundary visible para clearance).
    if options.show_courtyards:
        cy_pad = 0.5
        pieces.append(rect(
            fmt_num(x - cy_pad), fmt_num(y - cy_pad),
            fmt_num(fw + 2 * cy_pad), fmt_num(fh + 2 * cy_pad),
            **{"class": "courtyard"},
        ))

    # Cuerpo (silkscreen body outline).
    pieces.append(rect(
        fmt_num(x), fmt_num(y), fmt_num(fw), fmt_num(fh),
        **{"class": "fp-body"},
    ))

    # Silkscreen text (ref).
    if options.show_silkscreen:
        pieces.append(text(
            fmt_num(pos.x), fmt_num(y - 1.0),
            comp.ref,
            **{"class": "silk-ref", "text-anchor": "middle"},
        ))

    return group(
        "".join(pieces),
        **{"class": "footprint", "data-ref": comp.ref,
           "data-type": comp.type},
    )


# ────────────────────────────────────────────────────────────────────────────
# Estilos
# ────────────────────────────────────────────────────────────────────────────


_CSS_DARK = """
.pcb-bg { fill: #0e4a1a; }
.edge-cuts { fill: none; stroke: #d4af37; stroke-width: 0.3; }
.trace { fill: none; }
.layer-f-cu { stroke: #c87f3a; }
.layer-b-cu { stroke: #4a8fc8; opacity: 0.85; }
.via { fill: #c0c0c0; stroke: #999; stroke-width: 0.05; }
.via-drill { fill: #0e4a1a; stroke: none; }
.courtyard { fill: none; stroke: #ffeb3b; stroke-width: 0.1; stroke-dasharray: 0.4 0.3; opacity: 0.6; }
.fp-body { fill: rgba(255,255,255,0.05); stroke: #f5f5f5; stroke-width: 0.15; }
.silk-ref { font-family: sans-serif; font-size: 2px; fill: #f5f5f5; }
"""

_CSS_LIGHT = """
.pcb-bg { fill: #f5f1e0; }
.edge-cuts { fill: none; stroke: #444; stroke-width: 0.3; }
.trace { fill: none; }
.layer-f-cu { stroke: #c8553d; }
.layer-b-cu { stroke: #1f5fb3; opacity: 0.7; stroke-dasharray: 1 0.5; }
.via { fill: #999; stroke: #555; stroke-width: 0.05; }
.via-drill { fill: #f5f1e0; stroke: none; }
.courtyard { fill: none; stroke: #b8860b; stroke-width: 0.1; stroke-dasharray: 0.4 0.3; opacity: 0.5; }
.fp-body { fill: #fff8e1; stroke: #5a4a00; stroke-width: 0.2; }
.silk-ref { font-family: sans-serif; font-size: 2px; fill: #2a2a8a; font-weight: bold; }
"""
