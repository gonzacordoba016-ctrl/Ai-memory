"""
Routing Engine — generación determinista de traces ortogonales (Manhattan).

Reemplaza el routing implícito que hacían los renderers (`tools/eda/router.py`
+ `pcb_renderer._route_traces` + heurísticas star/H-V dispersas) por una capa
pura sin rendering ni placement.

Pipeline:
    1. Para cada net, calcular las posiciones de sus pines (por ahora =
       posición del componente, refinable con offsets reales en Fase 7).
    2. Construir un MST (Prim, tiebreak alfabético) sobre esas posiciones.
    3. Para cada arista del MST, intentar dos L-shapes Manhattan
       (H-then-V y V-then-H) y elegir la que tenga menos cruces con
       traces ya emitidas.
    4. Si el mejor candidato cruza traces en F.Cu, intentar B.Cu con vías
       en los endpoints.
    5. Asignar trace_width según net_class (signal / power / high_current).

Determinismo:
    - Nets ordenados alfabéticamente por nombre.
    - Edges del MST con tiebreak (peso, ref_a, ref_b).
    - Sin random.

API:
    route(circuit, options=None) → RoutingResult

Sin SVG. Sin placement. Solo traces y vías.
"""
from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field

from tools.eda.ir import (
    Circuit,
    DesignRules,
    Layer,
    Net,
    Severity,
    Trace,
    ValidationIssue,
    Vec2,
    Via,
)


# ────────────────────────────────────────────────────────────────────────────
# Options
# ────────────────────────────────────────────────────────────────────────────


class RoutingOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_layer: Layer = Layer.F_CU
    secondary_layer: Layer = Layer.B_CU
    enable_layer_swap: bool = True  # mover a B.Cu si hay cruces en F.Cu
    prefer_horizontal_first: bool = True


class RoutingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    circuit: Circuit
    issues: list[ValidationIssue] = Field(default_factory=list)
    nets_routed: int = 0
    traces_count: int = 0
    vias_count: int = 0
    crossings_unresolved: int = 0


# ────────────────────────────────────────────────────────────────────────────
# Net classification (para trace width)
# ────────────────────────────────────────────────────────────────────────────


_POWER_NET_KEYWORDS = (
    "vcc", "vdd", "vin", "5v", "3v3", "3.3v", "+5v", "+3.3v", "+5", "+3",
    "12v", "+12v", "24v", "+24v",
)
_GROUND_NET_KEYWORDS = ("gnd", "ground", "agnd", "dgnd", "pgnd")


def _net_class_inferred(net: Net) -> str:
    """Si el net no tiene class explícita, inferirla por keyword en el nombre."""
    cls = net.net_class
    if cls != "signal":
        return cls  # honra explícito (power, ground, high_current, etc.)
    name_l = net.name.lower()
    if any(kw in name_l for kw in _GROUND_NET_KEYWORDS):
        return "ground"
    if any(kw in name_l for kw in _POWER_NET_KEYWORDS):
        return "power"
    return "signal"


def _trace_width_for(net: Net, dr: DesignRules) -> float:
    cls = _net_class_inferred(net)
    if cls == "high_current":
        return dr.trace_width_high_current_mm
    if cls in ("power", "ground"):
        return dr.trace_width_power_mm
    return dr.trace_width_signal_mm


# ────────────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────────────


def route(
    circuit: Circuit,
    options: RoutingOptions | None = None,
) -> RoutingResult:
    options = options or RoutingOptions()
    dr = circuit.design_rules
    issues: list[ValidationIssue] = []

    # Mapa ref → posición del componente (centro). Componentes sin placement
    # quedan fuera y se reportan.
    pos_of: dict[str, Vec2] = {}
    for c in circuit.components:
        if c.placement is not None:
            pos_of[c.ref] = c.placement.position

    # Acumuladores de output (uno por layer para detección O(N) de cruces).
    traces_by_layer: dict[Layer, list[tuple[str, list[tuple[Vec2, Vec2]]]]] = {
        options.primary_layer: [],
        options.secondary_layer: [],
    }
    new_traces: list[Trace] = []
    new_vias: list[Via] = []
    via_positions_by_net: dict[str, set[tuple[float, float]]] = {}

    # Determinismo: nets en orden alfabético.
    sorted_nets = sorted(circuit.nets, key=lambda n: n.name)

    nets_routed = 0
    crossings_unresolved = 0

    for net in sorted_nets:
        # Listar refs únicas con placement.
        unique_refs: list[str] = []
        seen: set[str] = set()
        for node in net.nodes:
            if node.ref in pos_of and node.ref not in seen:
                unique_refs.append(node.ref)
                seen.add(node.ref)
        if len(unique_refs) < 2:
            # Net trivial: 0 o 1 nodo posicionado — nada que rutear.
            if any(n.ref not in pos_of for n in net.nodes):
                issues.append(ValidationIssue(
                    code="NET_NODE_UNPLACED",
                    severity=Severity.WARNING,
                    message=f"Net '{net.name}': uno o más nodos sin placement, "
                            f"trace omitida.",
                    net=net.name,
                    rule="routing_engine",
                ))
            continue

        nets_routed += 1
        width = _trace_width_for(net, dr)

        # MST sobre los pin positions (Prim determinista).
        edges = _build_mst(unique_refs, pos_of)

        for ref_a, ref_b in edges:
            pa = pos_of[ref_a]
            pb = pos_of[ref_b]
            best_path, best_layer, n_crossings = _choose_path_and_layer(
                pa, pb, options, traces_by_layer,
                allow_secondary=options.enable_layer_swap,
            )
            if best_path is None:
                crossings_unresolved += 1
                issues.append(ValidationIssue(
                    code="ROUTE_UNRESOLVABLE",
                    severity=Severity.ERROR,
                    message=f"Net '{net.name}': trace {ref_a}↔{ref_b} cruza "
                            f"otras en ambas capas; routing manual necesario.",
                    net=net.name,
                    rule="routing_engine",
                ))
                continue

            # Emitir trace.
            new_traces.append(Trace(
                net=net.name,
                points=list(best_path),
                width_mm=width,
                layer=best_layer,
            ))
            # Registrar segmentos para futuras detecciones.
            traces_by_layer[best_layer].append(
                (net.name, _segments_of(best_path))
            )

            # Vías cuando trace cae a B.Cu.
            if best_layer == options.secondary_layer:
                for ep in (best_path[0], best_path[-1]):
                    key = (round(ep.x, 4), round(ep.y, 4))
                    via_set = via_positions_by_net.setdefault(net.name, set())
                    if key in via_set:
                        continue
                    via_set.add(key)
                    new_vias.append(Via(
                        net=net.name,
                        position=ep,
                        drill_mm=dr.via_drill_mm,
                        diameter_mm=dr.via_diameter_mm,
                        from_layer=options.primary_layer,
                        to_layer=options.secondary_layer,
                    ))

    new_circuit = circuit.model_copy(update={
        "traces": list(circuit.traces) + new_traces,
        "vias": list(circuit.vias) + new_vias,
    })

    return RoutingResult(
        circuit=new_circuit,
        issues=issues,
        nets_routed=nets_routed,
        traces_count=len(new_traces),
        vias_count=len(new_vias),
        crossings_unresolved=crossings_unresolved,
    )


# ────────────────────────────────────────────────────────────────────────────
# MST (Prim determinista)
# ────────────────────────────────────────────────────────────────────────────


def _build_mst(
    refs: list[str],
    pos_of: dict[str, Vec2],
) -> list[tuple[str, str]]:
    """MST sobre el grafo completo de `refs`, peso = distancia Manhattan.

    Tiebreak determinista: (peso, ref_a, ref_b) en orden alfabético.
    """
    if len(refs) < 2:
        return []
    # Sort para arrancar siempre del mismo nodo.
    refs_sorted = sorted(refs)
    in_tree = {refs_sorted[0]}
    out_tree = set(refs_sorted[1:])
    edges: list[tuple[str, str]] = []

    while out_tree:
        best: tuple[float, str, str] | None = None
        for a in in_tree:
            pa = pos_of[a]
            for b in out_tree:
                pb = pos_of[b]
                w = abs(pa.x - pb.x) + abs(pa.y - pb.y)
                # Tiebreak: distancia, luego ref_a, luego ref_b.
                key = (w, a, b)
                if best is None or key < best:
                    best = key
        assert best is not None
        _, a, b = best
        edges.append((a, b))
        in_tree.add(b)
        out_tree.remove(b)
    return edges


# ────────────────────────────────────────────────────────────────────────────
# L-shape Manhattan + selección de capa
# ────────────────────────────────────────────────────────────────────────────


def _l_shapes(p0: Vec2, p1: Vec2) -> list[list[Vec2]]:
    """Dos candidatos Manhattan: H-then-V y V-then-H.

    Si los puntos están alineados ortogonalmente, ambos colapsan a un
    segmento — devolvemos uno solo en ese caso.
    """
    if p0.x == p1.x or p0.y == p1.y:
        return [[p0, p1]]
    h_then_v = [p0, Vec2(x=p1.x, y=p0.y), p1]
    v_then_h = [p0, Vec2(x=p0.x, y=p1.y), p1]
    return [h_then_v, v_then_h]


def _choose_path_and_layer(
    p0: Vec2,
    p1: Vec2,
    options: RoutingOptions,
    traces_by_layer: dict[Layer, list[tuple[str, list[tuple[Vec2, Vec2]]]]],
    *,
    allow_secondary: bool,
) -> tuple[list[Vec2] | None, Layer, int]:
    """Elige (path, layer, crossings_count) minimizando colisiones.

    Estrategia:
      1. Probar las 2 L-shapes en `primary_layer`.
      2. Si la mejor tiene 0 cruces → la usamos.
      3. Si no, probar las mismas en `secondary_layer`.
      4. Si la mejor del secundario tiene 0 cruces → la usamos.
      5. Si nada da 0 cruces, devolver la opción con menor cruce (preferimos
         primary) o (None, ...) si todas son inviables.
    """
    candidates = _l_shapes(p0, p1)
    # Ordenar candidatos para preferencia H-first si configurado.
    if not options.prefer_horizontal_first and len(candidates) > 1:
        candidates = list(reversed(candidates))

    def _eval(layer: Layer, path: list[Vec2]) -> int:
        my_segs = _segments_of(path)
        crossings = 0
        for _, seg_list in traces_by_layer.get(layer, []):
            for s_other in seg_list:
                for s_mine in my_segs:
                    if _segments_cross(s_mine, s_other):
                        crossings += 1
        return crossings

    # Buscar cero cruces en primary.
    for path in candidates:
        if _eval(options.primary_layer, path) == 0:
            return path, options.primary_layer, 0

    if allow_secondary:
        for path in candidates:
            if _eval(options.secondary_layer, path) == 0:
                return path, options.secondary_layer, 0

    # Fallback: menor cruce. Tiebreak por layer (primary < secondary)
    # luego por orden de candidato (estable).
    best_key: tuple[int, int, int] | None = None
    best_path: list[Vec2] | None = None
    best_layer: Layer = options.primary_layer
    for idx, path in enumerate(candidates):
        cr = _eval(options.primary_layer, path)
        key = (cr, 0, idx)  # 0 = primary
        if best_key is None or key < best_key:
            best_key = key
            best_path = path
            best_layer = options.primary_layer
    if allow_secondary:
        for idx, path in enumerate(candidates):
            cr = _eval(options.secondary_layer, path)
            key = (cr, 1, idx)  # 1 = secondary
            if best_key is None or key < best_key:
                best_key = key
                best_path = path
                best_layer = options.secondary_layer
    if best_path is None:
        return None, options.primary_layer, 0
    return best_path, best_layer, best_key[0]


# ────────────────────────────────────────────────────────────────────────────
# Segments + cross detection
# ────────────────────────────────────────────────────────────────────────────


def _segments_of(points: list[Vec2]) -> list[tuple[Vec2, Vec2]]:
    return [(points[i], points[i + 1]) for i in range(len(points) - 1)]


def _is_horizontal(s: tuple[Vec2, Vec2]) -> bool:
    return s[0].y == s[1].y


def _is_vertical(s: tuple[Vec2, Vec2]) -> bool:
    return s[0].x == s[1].x


def _segments_cross(
    a: tuple[Vec2, Vec2], b: tuple[Vec2, Vec2],
) -> bool:
    """¿Dos segmentos Manhattan se cruzan en interior?

    Un endpoint compartido NO cuenta como cruce (junction válido).
    """
    a_h = _is_horizontal(a)
    a_v = _is_vertical(a)
    b_h = _is_horizontal(b)
    b_v = _is_vertical(b)

    if a_h and b_h:
        if a[0].y != b[0].y:
            return False
        ax_min, ax_max = sorted([a[0].x, a[1].x])
        bx_min, bx_max = sorted([b[0].x, b[1].x])
        # Overlap real (más allá del endpoint compartido).
        return ax_min < bx_max and bx_min < ax_max and not (
            ax_max == bx_min or bx_max == ax_min
        )

    if a_v and b_v:
        if a[0].x != b[0].x:
            return False
        ay_min, ay_max = sorted([a[0].y, a[1].y])
        by_min, by_max = sorted([b[0].y, b[1].y])
        return ay_min < by_max and by_min < ay_max and not (
            ay_max == by_min or by_max == ay_min
        )

    # Mixto H + V.
    if a_h and b_v:
        h, v = a, b
    elif a_v and b_h:
        h, v = b, a
    else:
        return False

    hx_min, hx_max = sorted([h[0].x, h[1].x])
    vy_min, vy_max = sorted([v[0].y, v[1].y])
    cross_x = v[0].x
    cross_y = h[0].y
    inside_h = hx_min < cross_x < hx_max
    inside_v = vy_min < cross_y < vy_max
    if inside_h and inside_v:
        return True
    return False
