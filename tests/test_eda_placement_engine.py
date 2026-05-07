"""Tests del Placement Engine — clasificación, packing, colisiones, determinismo."""
from __future__ import annotations

from tools.eda.ir import Circuit, Component, Net, Node
from tools.eda.placement_engine import (
    PlacementOptions,
    PlacementResult,
    Zone,
    place,
)


# ── Helpers ─────────────────────────────────────────────────────────────────


def _zones_of(result: PlacementResult) -> dict[str, str]:
    return result.zone_assignments


def _placed(result: PlacementResult, ref: str):
    for c in result.circuit.components:
        if c.ref == ref:
            return c.placement
    return None


# ── Clasificación por zona ─────────────────────────────────────────────────


def test_mcu_goes_to_mcu_zone():
    c = Circuit(components=[Component(ref="U1", type="esp32")])
    r = place(c)
    assert _zones_of(r)["U1"] == "mcu"


def test_sensor_goes_to_input_zone():
    c = Circuit(components=[
        Component(ref="U1", type="esp32"),
        Component(ref="S1", type="dht22"),
    ])
    r = place(c)
    assert _zones_of(r)["S1"] == "input"


def test_power_regulator_goes_to_power_zone():
    c = Circuit(components=[
        Component(ref="U1", type="arduino_uno"),
        Component(ref="REG", type="lm7805"),
    ])
    r = place(c)
    assert _zones_of(r)["REG"] == "power"


def test_display_goes_to_comm_zone():
    c = Circuit(components=[
        Component(ref="U1", type="esp32"),
        Component(ref="D1", type="oled_ssd1306"),
    ])
    r = place(c)
    assert _zones_of(r)["D1"] == "comm"


def test_motor_driver_goes_to_output_zone():
    c = Circuit(components=[
        Component(ref="U1", type="arduino_uno"),
        Component(ref="DRV", type="l298n"),
    ])
    r = place(c)
    assert _zones_of(r)["DRV"] == "output"


def test_relay_goes_to_output_zone():
    c = Circuit(components=[
        Component(ref="U1", type="esp32"),
        Component(ref="RL1", type="relay_module"),
    ])
    r = place(c)
    assert _zones_of(r)["RL1"] == "output"


def test_rtc_goes_to_comm_zone():
    c = Circuit(components=[
        Component(ref="U1", type="esp32"),
        Component(ref="RTC", type="ds3231"),
    ])
    r = place(c)
    assert _zones_of(r)["RTC"] == "comm"


def test_passive_goes_to_passive_zone():
    c = Circuit(components=[
        Component(ref="U1", type="esp32"),
        Component(ref="R1", type="resistor"),
        Component(ref="C1", type="capacitor"),
    ])
    r = place(c)
    assert _zones_of(r)["R1"] == "passive"
    assert _zones_of(r)["C1"] == "passive"


def test_ac_connector_goes_to_power_zone():
    c = Circuit(components=[
        Component(ref="J1", type="connector", value="220VAC mains"),
    ])
    r = place(c)
    assert _zones_of(r)["J1"] == "power"


# ── Coordenadas asignadas ──────────────────────────────────────────────────


def test_every_component_gets_placement():
    c = Circuit(components=[
        Component(ref="U1", type="esp32"),
        Component(ref="S1", type="dht22"),
        Component(ref="R1", type="resistor"),
        Component(ref="DRV", type="l298n"),
        Component(ref="REG", type="lm7805"),
        Component(ref="D1", type="oled_ssd1306"),
    ])
    r = place(c)
    for c in r.circuit.components:
        assert c.placement is not None, f"Sin placement: {c.ref}"


def test_placement_within_board():
    c = Circuit(components=[
        Component(ref="U1", type="esp32"),
        Component(ref="S1", type="dht22"),
    ])
    r = place(c)
    board = r.circuit.board
    assert board is not None
    for comp in r.circuit.components:
        p = comp.placement.position
        assert 0 <= p.x <= board.width_mm
        assert 0 <= p.y <= board.height_mm


def test_zones_are_spatially_separated():
    """MCU center, INPUT a la izquierda, OUTPUT a la derecha."""
    c = Circuit(components=[
        Component(ref="U1", type="esp32"),
        Component(ref="S1", type="dht22"),
        Component(ref="DRV", type="l298n"),
    ])
    r = place(c)
    p_mcu = _placed(r, "U1").position
    p_in = _placed(r, "S1").position
    p_out = _placed(r, "DRV").position
    assert p_in.x < p_mcu.x
    assert p_out.x > p_mcu.x


def test_power_above_mcu():
    c = Circuit(components=[
        Component(ref="U1", type="esp32"),
        Component(ref="REG", type="lm7805"),
    ])
    r = place(c)
    assert _placed(r, "REG").position.y < _placed(r, "U1").position.y


def test_passive_below_mcu():
    c = Circuit(components=[
        Component(ref="U1", type="esp32"),
        Component(ref="R1", type="resistor"),
    ])
    r = place(c)
    assert _placed(r, "R1").position.y > _placed(r, "U1").position.y


# ── Determinismo ──────────────────────────────────────────────────────────


def test_placement_is_deterministic():
    components = [
        Component(ref="U1", type="esp32"),
        Component(ref="S1", type="dht22"),
        Component(ref="S2", type="bmp280"),
        Component(ref="R1", type="resistor"),
        Component(ref="R2", type="resistor"),
        Component(ref="DRV", type="l298n"),
    ]
    c = Circuit(components=components)
    r1 = place(c)
    r2 = place(c)
    for ref in (c.ref for c in components):
        p1 = _placed(r1, ref).position
        p2 = _placed(r2, ref).position
        assert p1 == p2


def test_placement_independent_of_component_input_order():
    """Mismo conjunto de componentes (orden distinto) → mismas coords."""
    setA = [Component(ref="A", type="resistor"),
            Component(ref="B", type="resistor"),
            Component(ref="U1", type="esp32")]
    setB = [Component(ref="U1", type="esp32"),
            Component(ref="B", type="resistor"),
            Component(ref="A", type="resistor")]
    rA = place(Circuit(components=setA))
    rB = place(Circuit(components=setB))
    for ref in ("A", "B", "U1"):
        assert _placed(rA, ref).position == _placed(rB, ref).position


# ── Sin colisiones ──────────────────────────────────────────────────────────


def test_no_overlap_for_standard_circuits():
    """Circuito típico no produce overlaps."""
    c = Circuit(components=[
        Component(ref="U1", type="esp32"),
        Component(ref="S1", type="dht22"),
        Component(ref="S2", type="bmp280"),
        Component(ref="DRV", type="l298n"),
        Component(ref="REG", type="lm7805"),
        Component(ref="D1", type="oled_ssd1306"),
        Component(ref="R1", type="resistor"),
        Component(ref="R2", type="resistor"),
        Component(ref="C1", type="capacitor_electrolytic"),
    ])
    r = place(c)
    overlap_issues = [i for i in r.issues if i.code == "PLACEMENT_OVERLAP"]
    assert overlap_issues == []


# ── Snap to grid ──────────────────────────────────────────────────────────


def test_positions_snapped_to_grid():
    c = Circuit(components=[
        Component(ref="U1", type="esp32"),
        Component(ref="S1", type="dht22"),
    ])
    grid = 2.54
    r = place(c, PlacementOptions(grid_mm=grid))
    for comp in r.circuit.components:
        p = comp.placement.position
        # Cada coord debe ser múltiplo de grid (con tolerancia float).
        assert abs((p.x / grid) - round(p.x / grid)) < 1e-6
        assert abs((p.y / grid) - round(p.y / grid)) < 1e-6


# ── Auto-grow ─────────────────────────────────────────────────────────────


def test_auto_grow_for_many_components():
    """Muchos componentes con board chiquita — debería crecer."""
    comps = [Component(ref=f"R{i}", type="resistor") for i in range(60)]
    comps.append(Component(ref="U1", type="esp32"))
    c = Circuit(components=comps)
    r = place(c, PlacementOptions(
        initial_board_width_mm=40.0,
        initial_board_height_mm=30.0,
        auto_grow=True,
    ))
    assert r.circuit.board.width_mm > 40.0
    overflow = [i for i in r.issues if i.code == "ZONE_OVERFLOW"]
    assert overflow == []


def test_no_grow_when_disabled_marks_overflow():
    comps = [Component(ref=f"R{i}", type="resistor") for i in range(60)]
    c = Circuit(components=comps)
    r = place(c, PlacementOptions(
        initial_board_width_mm=20.0,
        initial_board_height_mm=20.0,
        auto_grow=False,
    ))
    overflow = [i for i in r.issues if i.code == "ZONE_OVERFLOW"]
    assert overflow != []


# ── Idempotencia ──────────────────────────────────────────────────────────


def test_placement_preserves_circuit_semantics():
    """El placement no debe alterar componentes ni nets — solo agrega coords."""
    c = Circuit(
        components=[
            Component(ref="U1", type="esp32"),
            Component(ref="S1", type="dht22"),
        ],
        nets=[
            Net(name="DATA", nodes=[Node(ref="U1", pin="GPIO16"),
                                     Node(ref="S1", pin="DATA")]),
        ],
    )
    r = place(c)
    # Mismo set de componentes.
    refs_in = {c.ref for c in c.components}
    refs_out = {c.ref for c in r.circuit.components}
    assert refs_in == refs_out
    # Mismo set de nets y conexiones.
    nets_in = {(n.name, frozenset((nd.ref, nd.pin) for nd in n.nodes))
               for n in c.nets}
    nets_out = {(n.name, frozenset((nd.ref, nd.pin) for nd in n.nodes))
                for n in r.circuit.nets}
    assert nets_in == nets_out


def test_circuit_passes_validation_after_place():
    c = Circuit(components=[
        Component(ref="U1", type="esp32"),
        Component(ref="S1", type="dht22"),
        Component(ref="R1", type="resistor"),
    ])
    r = place(c)
    Circuit.from_json(r.circuit.to_json())


# ── Bbox y board ──────────────────────────────────────────────────────────


def test_bbox_used_is_positive():
    c = Circuit(components=[Component(ref="U1", type="esp32")])
    r = place(c)
    assert r.bbox_used.x > 0
    assert r.bbox_used.y > 0


def test_board_assigned_when_missing():
    c = Circuit(components=[Component(ref="U1", type="esp32")])
    assert c.board is None
    r = place(c)
    assert r.circuit.board is not None
