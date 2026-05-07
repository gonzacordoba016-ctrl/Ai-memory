"""Tests del Routing Engine — Manhattan, MST, multi-layer, vias, widths."""
from __future__ import annotations

from tools.eda.ir import (
    Circuit,
    Component,
    DesignRules,
    Layer,
    Net,
    Node,
    PlacementInfo,
    Vec2,
)
from tools.eda.routing_engine import (
    RoutingOptions,
    RoutingResult,
    _l_shapes,
    _segments_cross,
    route,
)


# ── Helpers ─────────────────────────────────────────────────────────────────


def _placed(ref: str, type_: str, x: float, y: float) -> Component:
    return Component(ref=ref, type=type_,
                     placement=PlacementInfo(position=Vec2(x=x, y=y)))


def _trace_for_net(result: RoutingResult, net_name: str):
    return [t for t in result.circuit.traces if t.net == net_name]


# ── Manhattan path generation ──────────────────────────────────────────────


def test_l_shape_two_candidates_for_diagonal():
    paths = _l_shapes(Vec2(x=0, y=0), Vec2(x=10, y=5))
    assert len(paths) == 2
    # H-then-V: (0,0) → (10,0) → (10,5)
    assert paths[0] == [Vec2(x=0, y=0), Vec2(x=10, y=0), Vec2(x=10, y=5)]
    # V-then-H: (0,0) → (0,5) → (10,5)
    assert paths[1] == [Vec2(x=0, y=0), Vec2(x=0, y=5), Vec2(x=10, y=5)]


def test_l_shape_collapses_when_aligned():
    # Mismo X o mismo Y → 1 sola opción (segmento recto).
    paths = _l_shapes(Vec2(x=0, y=0), Vec2(x=10, y=0))
    assert len(paths) == 1
    paths = _l_shapes(Vec2(x=5, y=0), Vec2(x=5, y=10))
    assert len(paths) == 1


# ── Cross detection ───────────────────────────────────────────────────────


def test_segments_cross_orthogonal():
    h = (Vec2(x=0, y=5), Vec2(x=10, y=5))
    v = (Vec2(x=5, y=0), Vec2(x=5, y=10))
    assert _segments_cross(h, v)
    assert _segments_cross(v, h)


def test_segments_dont_cross_when_endpoint_shared():
    # H termina donde V empieza — junction, no cruce.
    h = (Vec2(x=0, y=0), Vec2(x=5, y=0))
    v = (Vec2(x=5, y=0), Vec2(x=5, y=10))
    assert not _segments_cross(h, v)


def test_segments_dont_cross_when_separated():
    h = (Vec2(x=0, y=5), Vec2(x=10, y=5))
    v = (Vec2(x=20, y=0), Vec2(x=20, y=10))
    assert not _segments_cross(h, v)


def test_parallel_horizontal_overlap():
    a = (Vec2(x=0, y=5), Vec2(x=10, y=5))
    b = (Vec2(x=5, y=5), Vec2(x=15, y=5))
    assert _segments_cross(a, b)


def test_parallel_horizontal_collinear_no_overlap():
    a = (Vec2(x=0, y=5), Vec2(x=5, y=5))
    b = (Vec2(x=5, y=5), Vec2(x=10, y=5))
    assert not _segments_cross(a, b)  # endpoint compartido


# ── Routing simple ────────────────────────────────────────────────────────


def test_single_net_two_components_one_trace():
    c = Circuit(
        components=[
            _placed("U1", "esp32",   x=10.0, y=10.0),
            _placed("LED1", "led",   x=30.0, y=20.0),
        ],
        nets=[
            Net(name="LED_DRIVE", nodes=[Node(ref="U1", pin="GPIO2"),
                                           Node(ref="LED1", pin="anode")]),
        ],
    )
    r = route(c)
    assert r.nets_routed == 1
    assert r.traces_count == 1
    assert r.vias_count == 0
    traces = _trace_for_net(r, "LED_DRIVE")
    assert len(traces) == 1
    assert traces[0].layer == Layer.F_CU


def test_three_node_net_yields_two_traces():
    """MST sobre 3 nodos = 2 aristas."""
    c = Circuit(
        components=[
            _placed("U1", "esp32",  x=10.0, y=10.0),
            _placed("R1", "resistor", x=20.0, y=10.0),
            _placed("L1", "led",   x=30.0, y=10.0),
        ],
        nets=[
            Net(name="X", nodes=[Node(ref="U1", pin="GPIO2"),
                                  Node(ref="R1", pin="1"),
                                  Node(ref="L1", pin="anode")]),
        ],
    )
    r = route(c)
    assert r.traces_count == 2


def test_net_with_one_node_emits_no_trace():
    c = Circuit(
        components=[_placed("U1", "esp32", x=0, y=0)],
        nets=[Net(name="VCC", nodes=[Node(ref="U1", pin="VCC")])],
    )
    r = route(c)
    assert r.traces_count == 0
    assert r.nets_routed == 0


def test_unplaced_component_yields_warning():
    c = Circuit(
        components=[
            Component(ref="U1", type="esp32",
                       placement=PlacementInfo(position=Vec2(x=0, y=0))),
            Component(ref="X1", type="resistor"),  # sin placement
        ],
        nets=[Net(name="N", nodes=[Node(ref="U1", pin="GPIO2"),
                                     Node(ref="X1", pin="1")])],
    )
    r = route(c)
    assert any(i.code == "NET_NODE_UNPLACED" for i in r.issues)


# ── Multi-layer / vias ────────────────────────────────────────────────────


def test_crossing_nets_use_two_layers():
    """Dos nets que se cruzan → la segunda va a B.Cu con vías."""
    c = Circuit(
        components=[
            _placed("A1", "resistor", x=0.0, y=0.0),
            _placed("A2", "resistor", x=20.0, y=0.0),
            _placed("B1", "resistor", x=10.0, y=-10.0),
            _placed("B2", "resistor", x=10.0, y=10.0),
        ],
        nets=[
            # Horizontal (A1—A2) y vertical (B1—B2) que se cruzan en (10,0).
            Net(name="HORIZ", nodes=[Node(ref="A1", pin="1"),
                                       Node(ref="A2", pin="1")]),
            Net(name="VERT", nodes=[Node(ref="B1", pin="1"),
                                      Node(ref="B2", pin="1")]),
        ],
    )
    r = route(c)
    assert r.traces_count == 2
    layers = {t.layer for t in r.circuit.traces}
    # Una en F.Cu, otra en B.Cu.
    assert Layer.F_CU in layers
    assert Layer.B_CU in layers
    # Vías en los 2 endpoints del trace en B.Cu.
    assert r.vias_count == 2


def test_layer_swap_disabled_keeps_everything_on_primary():
    c = Circuit(
        components=[
            _placed("A1", "resistor", x=0.0, y=0.0),
            _placed("A2", "resistor", x=20.0, y=0.0),
            _placed("B1", "resistor", x=10.0, y=-10.0),
            _placed("B2", "resistor", x=10.0, y=10.0),
        ],
        nets=[
            Net(name="A", nodes=[Node(ref="A1", pin="1"),
                                  Node(ref="A2", pin="1")]),
            Net(name="B", nodes=[Node(ref="B1", pin="1"),
                                  Node(ref="B2", pin="1")]),
        ],
    )
    r = route(c, RoutingOptions(enable_layer_swap=False))
    assert r.vias_count == 0
    # Todas en primary.
    layers = {t.layer for t in r.circuit.traces}
    assert layers == {Layer.F_CU}


# ── Trace width por net_class ─────────────────────────────────────────────


def test_power_net_uses_power_width():
    dr = DesignRules(trace_width_signal_mm=0.25, trace_width_power_mm=0.5)
    c = Circuit(
        components=[
            _placed("U1", "esp32", x=0.0, y=0.0),
            _placed("REG", "lm7805", x=20.0, y=0.0),
        ],
        nets=[
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC"),
                                     Node(ref="REG", pin="OUT")]),
        ],
        design_rules=dr,
    )
    r = route(c)
    t = _trace_for_net(r, "VCC")[0]
    assert t.width_mm == 0.5


def test_signal_net_uses_signal_width():
    dr = DesignRules(trace_width_signal_mm=0.25, trace_width_power_mm=0.5)
    c = Circuit(
        components=[
            _placed("U1", "esp32", x=0.0, y=0.0),
            _placed("S1", "dht22", x=20.0, y=0.0),
        ],
        nets=[
            Net(name="DATA", nodes=[Node(ref="U1", pin="GPIO16"),
                                      Node(ref="S1", pin="DATA")]),
        ],
        design_rules=dr,
    )
    r = route(c)
    t = _trace_for_net(r, "DATA")[0]
    assert t.width_mm == 0.25


def test_high_current_class_uses_widest():
    dr = DesignRules(
        trace_width_signal_mm=0.25,
        trace_width_power_mm=0.5,
        trace_width_high_current_mm=1.0,
    )
    c = Circuit(
        components=[
            _placed("DRV", "l298n", x=0.0, y=0.0),
            _placed("M1", "motor", x=20.0, y=0.0),
        ],
        nets=[
            Net(name="MOTOR_OUT", net_class="high_current",
                nodes=[Node(ref="DRV", pin="OUT1"),
                       Node(ref="M1", pin="1")]),
        ],
        design_rules=dr,
    )
    r = route(c)
    t = _trace_for_net(r, "MOTOR_OUT")[0]
    assert t.width_mm == 1.0


def test_gnd_net_inferred_as_power():
    """Net 'GND' sin net_class explícito debe usar power width."""
    dr = DesignRules(trace_width_signal_mm=0.25, trace_width_power_mm=0.5)
    c = Circuit(
        components=[
            _placed("U1", "esp32", x=0.0, y=0.0),
            _placed("R1", "resistor", x=10.0, y=0.0),
        ],
        nets=[
            Net(name="GND", nodes=[Node(ref="U1", pin="GND"),
                                    Node(ref="R1", pin="2")]),
        ],
        design_rules=dr,
    )
    r = route(c)
    t = _trace_for_net(r, "GND")[0]
    assert t.width_mm == 0.5


# ── Determinismo ──────────────────────────────────────────────────────────


def test_routing_is_deterministic():
    c = Circuit(
        components=[
            _placed("U1", "esp32",   x=10.0, y=10.0),
            _placed("S1", "dht22",   x=30.0, y=20.0),
            _placed("R1", "resistor", x=20.0, y=15.0),
            _placed("D1", "led",     x=40.0, y=10.0),
        ],
        nets=[
            Net(name="A", nodes=[Node(ref="U1", pin="GPIO2"),
                                  Node(ref="R1", pin="1")]),
            Net(name="B", nodes=[Node(ref="R1", pin="2"),
                                  Node(ref="D1", pin="anode")]),
            Net(name="C", nodes=[Node(ref="U1", pin="GPIO5"),
                                  Node(ref="S1", pin="DATA")]),
        ],
    )
    r1 = route(c)
    r2 = route(c)
    # Mismo número de traces y vías.
    assert r1.traces_count == r2.traces_count
    assert r1.vias_count == r2.vias_count
    # Mismas coords.
    for t1, t2 in zip(r1.circuit.traces, r2.circuit.traces):
        assert t1.points == t2.points
        assert t1.layer == t2.layer


# ── Manhattan-only ────────────────────────────────────────────────────────


def test_traces_are_axis_aligned():
    c = Circuit(
        components=[
            _placed("U1", "esp32", x=0.0, y=0.0),
            _placed("S1", "dht22", x=37.0, y=23.0),
        ],
        nets=[
            Net(name="X", nodes=[Node(ref="U1", pin="GPIO2"),
                                  Node(ref="S1", pin="DATA")]),
        ],
    )
    r = route(c)
    for t in r.circuit.traces:
        for i in range(len(t.points) - 1):
            p, q = t.points[i], t.points[i + 1]
            assert p.x == q.x or p.y == q.y, \
                f"Segmento no axis-aligned: {p} → {q}"


# ── Idempotencia ──────────────────────────────────────────────────────────


def test_routing_preserves_components_and_nets():
    c = Circuit(
        components=[
            _placed("U1", "esp32", x=0.0, y=0.0),
            _placed("S1", "dht22", x=20.0, y=10.0),
        ],
        nets=[
            Net(name="N", nodes=[Node(ref="U1", pin="GPIO16"),
                                  Node(ref="S1", pin="DATA")]),
        ],
    )
    r = route(c)
    assert {c.ref for c in r.circuit.components} == {"U1", "S1"}
    assert [n.name for n in r.circuit.nets] == ["N"]


def test_circuit_passes_validation_after_routing():
    c = Circuit(
        components=[
            _placed("U1", "esp32", x=0.0, y=0.0),
            _placed("S1", "dht22", x=20.0, y=10.0),
        ],
        nets=[
            Net(name="N", nodes=[Node(ref="U1", pin="GPIO16"),
                                  Node(ref="S1", pin="DATA")]),
        ],
    )
    r = route(c)
    Circuit.from_json(r.circuit.to_json())
