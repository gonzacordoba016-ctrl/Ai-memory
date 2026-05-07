"""Tests del Circuit IR — validación, lookups, JSON roundtrip."""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from tools.eda.ir import (
    Circuit,
    CircuitMetadata,
    Component,
    DesignRules,
    ElectricalType,
    Layer,
    Net,
    Node,
    Pin,
    PlacementInfo,
    Severity,
    Side,
    Trace,
    ValidationIssue,
    Vec2,
)


# ── Vec2 ────────────────────────────────────────────────────────────────────


def test_vec2_arithmetic():
    a = Vec2(x=1.0, y=2.0)
    b = Vec2(x=3.0, y=4.0)
    assert (a + b) == Vec2(x=4.0, y=6.0)
    assert (b - a) == Vec2(x=2.0, y=2.0)


def test_vec2_frozen():
    v = Vec2(x=1.0, y=2.0)
    with pytest.raises(ValidationError):
        v.x = 99.0  # type: ignore[misc]


# ── Pin ─────────────────────────────────────────────────────────────────────


def test_pin_default_electrical_type():
    p = Pin(number="1", name="A")
    assert p.electrical_type == ElectricalType.UNSPECIFIED


def test_pin_with_functions():
    p = Pin(number="GPIO21", name="GPIO21", electrical_type=ElectricalType.BIDIRECTIONAL,
            functions=["I2C_SDA", "GPIO"])
    assert "I2C_SDA" in p.functions


# ── Component ───────────────────────────────────────────────────────────────


def test_component_lookup_by_pin():
    c = Component(ref="U1", type="esp32",
                  pins=[Pin(number="GPIO21", name="GPIO21"),
                        Pin(number="GPIO22", name="GPIO22")])
    assert c.pin("GPIO21") is not None
    assert c.pin("GPIO99") is None


def test_component_no_dup_pins():
    with pytest.raises(ValidationError):
        Component(ref="U1", type="x",
                  pins=[Pin(number="1", name="a"), Pin(number="1", name="b")])


def test_component_ref_pattern():
    # Refs deben ser identificadores válidos.
    Component(ref="U1", type="x")
    Component(ref="R_99", type="x")
    with pytest.raises(ValidationError):
        Component(ref="1U", type="x")  # empieza con dígito
    with pytest.raises(ValidationError):
        Component(ref="U-1", type="x")  # guion no permitido


# ── Net ─────────────────────────────────────────────────────────────────────


def test_net_no_dup_nodes():
    with pytest.raises(ValidationError):
        Net(name="VCC", nodes=[Node(ref="U1", pin="VCC"), Node(ref="U1", pin="VCC")])


def test_net_default_class():
    n = Net(name="VCC")
    assert n.net_class == "signal"


# ── Circuit ─────────────────────────────────────────────────────────────────


def test_circuit_unique_refs():
    with pytest.raises(ValidationError):
        Circuit(components=[Component(ref="U1", type="esp32"),
                            Component(ref="U1", type="arduino_uno")])


def test_circuit_unique_net_names():
    with pytest.raises(ValidationError):
        Circuit(nets=[Net(name="VCC"), Net(name="VCC")])


def test_circuit_node_refs_must_exist():
    with pytest.raises(ValidationError):
        Circuit(
            components=[Component(ref="U1", type="esp32")],
            nets=[Net(name="VCC", nodes=[Node(ref="U99", pin="VCC")])],
        )


def test_circuit_lookups():
    c = Circuit(
        components=[
            Component(ref="U1", type="esp32"),
            Component(ref="R1", type="resistor"),
        ],
        nets=[
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC"),
                                    Node(ref="R1", pin="1")]),
        ],
    )
    assert c.component("U1") is not None
    assert c.component("X") is None
    assert c.net("VCC") is not None
    assert {n.name for n in c.nets_of("R1")} == {"VCC"}


# ── Roundtrip JSON ──────────────────────────────────────────────────────────


def test_circuit_json_roundtrip():
    original = Circuit(
        metadata=CircuitMetadata(title="blink", mcu="esp32"),
        components=[
            Component(ref="U1", type="esp32",
                      pins=[Pin(number="GPIO2", name="GPIO2",
                                electrical_type=ElectricalType.BIDIRECTIONAL)],
                      placement=PlacementInfo(position=Vec2(x=10.0, y=20.0),
                                              rotation_deg=90)),
            Component(ref="LED1", type="led"),
            Component(ref="R1", type="resistor", value="220"),
        ],
        nets=[
            Net(name="GPIO2", net_class="signal",
                nodes=[Node(ref="U1", pin="GPIO2"),
                       Node(ref="R1", pin="1")]),
            Net(name="LED_K", nodes=[Node(ref="R1", pin="2"),
                                      Node(ref="LED1", pin="anode")]),
            Net(name="GND", nodes=[Node(ref="LED1", pin="cathode")]),
        ],
        traces=[
            Trace(net="GPIO2",
                  points=[Vec2(x=0.0, y=0.0), Vec2(x=10.0, y=0.0)],
                  width_mm=0.25, layer=Layer.F_CU),
        ],
    )
    serialized = original.to_json()
    parsed = json.loads(serialized)
    # Sanity sobre el JSON.
    assert parsed["metadata"]["title"] == "blink"
    # Roundtrip semántico.
    rebuilt = Circuit.from_json(serialized)
    assert rebuilt.model_dump() == original.model_dump()


# ── PlacementInfo ──────────────────────────────────────────────────────────


def test_placement_rotation_normalized():
    p = PlacementInfo(position=Vec2(x=0, y=0), rotation_deg=720)
    assert p.rotation_deg == 0.0
    p2 = PlacementInfo(position=Vec2(x=0, y=0), rotation_deg=-90)
    assert p2.rotation_deg == 270.0


def test_placement_default_side():
    p = PlacementInfo(position=Vec2(x=0, y=0))
    assert p.side == Side.TOP


# ── Trace ──────────────────────────────────────────────────────────────────


def test_trace_requires_two_points():
    with pytest.raises(ValidationError):
        Trace(net="X", points=[Vec2(x=0, y=0)], width_mm=0.25)


def test_trace_width_positive():
    with pytest.raises(ValidationError):
        Trace(net="X", points=[Vec2(x=0, y=0), Vec2(x=1, y=1)], width_mm=0)


# ── DesignRules ────────────────────────────────────────────────────────────


def test_design_rules_defaults():
    d = DesignRules()
    assert d.clearance_mm > 0
    assert d.trace_width_signal_mm < d.trace_width_power_mm


# ── ValidationIssue ────────────────────────────────────────────────────────


def test_validation_issue_serializes():
    iss = ValidationIssue(code="X", severity=Severity.ERROR,
                          message="boom", component="U1")
    d = iss.model_dump(exclude_none=True)
    assert d["severity"] == "error"
    assert "net" not in d
