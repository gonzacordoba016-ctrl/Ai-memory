"""Tests de los exporters — kicad_sch + kicad_pcb + bom."""
from __future__ import annotations

import csv
import io

import pytest

from tools.eda.export import (
    BOMRow,
    export_kicad_pcb,
    export_kicad_sch,
    render_bom_csv,
)
from tools.eda.export.bom import render_bom
from tools.eda.ir import (
    Board,
    Circuit,
    Component,
    Layer,
    Net,
    Node,
    PlacementInfo,
    Trace,
    Vec2,
    Via,
)


def _placed(ref, type_, x, y, value=None) -> Component:
    return Component(
        ref=ref, type=type_,
        value=value,
        placement=PlacementInfo(position=Vec2(x=x, y=y)),
    )


def _basic_placed_circuit() -> Circuit:
    return Circuit(
        components=[
            _placed("U1", "esp32", 50, 40),
            _placed("R1", "resistor", 30, 40, value="220"),
            _placed("R2", "resistor", 70, 40, value="220"),
            _placed("LED1", "led", 30, 60),
        ],
        nets=[
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND"),
                                    Node(ref="LED1", pin="cathode")]),
            Net(name="DRIVE", nodes=[Node(ref="U1", pin="GPIO2"),
                                       Node(ref="R1", pin="1")]),
            Net(name="LED_K", nodes=[Node(ref="R1", pin="2"),
                                       Node(ref="LED1", pin="anode")]),
        ],
        traces=[
            Trace(net="DRIVE", points=[Vec2(x=30, y=40), Vec2(x=50, y=40)],
                  width_mm=0.25, layer=Layer.F_CU),
        ],
        vias=[
            Via(net="GND", position=Vec2(x=40, y=50),
                drill_mm=0.4, diameter_mm=0.8),
        ],
        board=Board(width_mm=100, height_mm=80),
    )


# ─── BOM ──────────────────────────────────────────────────────────────────


def test_bom_groups_by_type_value_footprint():
    rows = render_bom(_basic_placed_circuit())
    # esp32, led, 2x resistor 220 (group), 4 unique components → 3 rows.
    assert len(rows) == 3
    res_row = next(r for r in rows if r.type == "resistor")
    assert res_row.quantity == 2
    assert res_row.references == ["R1", "R2"]


def test_bom_csv_format():
    csv_text = render_bom_csv(_basic_placed_circuit())
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    assert "References" in reader.fieldnames
    assert "Quantity" in reader.fieldnames
    types = {r["Type"] for r in rows}
    assert "esp32" in types
    assert "resistor" in types
    assert "led" in types


def test_bom_includes_footprint_from_registry():
    rows = render_bom(_basic_placed_circuit())
    res_row = next(r for r in rows if r.type == "resistor")
    assert "Resistor_THT" in res_row.footprint


# ─── KiCad sch ────────────────────────────────────────────────────────────


def test_kicad_sch_emits_header():
    out = export_kicad_sch(_basic_placed_circuit())
    assert "(kicad_sch" in out
    assert "(generator stratum_eda)" in out
    assert "(version 20211123)" in out


def test_kicad_sch_balanced_parens():
    out = export_kicad_sch(_basic_placed_circuit())
    assert out.count("(") == out.count(")")


def test_kicad_sch_includes_all_components():
    out = export_kicad_sch(_basic_placed_circuit())
    for ref in ("U1", "R1", "R2", "LED1"):
        assert f'"{ref}"' in out


def test_kicad_sch_lib_symbols_per_unique_type():
    out = export_kicad_sch(_basic_placed_circuit())
    # Hay 3 types únicos: esp32, resistor, led.
    assert out.count("(symbol \"Stratum:esp32\"") >= 1
    assert out.count("(symbol \"Stratum:resistor\"") >= 1
    assert out.count("(symbol \"Stratum:led\"") >= 1


def test_kicad_sch_emits_wires_for_multinode_nets():
    out = export_kicad_sch(_basic_placed_circuit())
    # GND (2 nodos), DRIVE (2 nodos), LED_K (2 nodos) → wires.
    assert out.count("(wire ") >= 3


def test_kicad_sch_has_net_labels():
    out = export_kicad_sch(_basic_placed_circuit())
    assert '(label "GND"' in out
    assert '(label "DRIVE"' in out


def test_kicad_sch_deterministic():
    c = _basic_placed_circuit()
    a = export_kicad_sch(c)
    b = export_kicad_sch(c)
    assert a == b


def test_kicad_sch_skips_components_without_placement():
    c = Circuit(
        components=[
            _placed("U1", "esp32", 50, 40),
            Component(ref="X1", type="resistor"),
        ],
        nets=[],
    )
    out = export_kicad_sch(c)
    assert '"U1"' in out
    # X1 no debe aparecer en symbol instances (su lib_symbol sí porque está
    # en el set de tipos).
    assert "X1" not in out.split("(lib_symbols")[1].split("(lib_symbols")[0] \
        if "(lib_symbols" in out else True
    # Mejor: no hay (symbol (lib_id ...) (at ...) ) instance para X1.
    assert "(at" in out  # at least U1 placed


# ─── KiCad pcb ────────────────────────────────────────────────────────────


def test_kicad_pcb_requires_board():
    c = Circuit(components=[_placed("U1", "esp32", 0, 0)])
    with pytest.raises(ValueError):
        export_kicad_pcb(c)


def test_kicad_pcb_emits_header():
    out = export_kicad_pcb(_basic_placed_circuit())
    assert "(kicad_pcb" in out
    assert "(generator stratum_eda)" in out
    assert "(version 20221018)" in out


def test_kicad_pcb_balanced_parens():
    out = export_kicad_pcb(_basic_placed_circuit())
    assert out.count("(") == out.count(")")


def test_kicad_pcb_layers_present():
    out = export_kicad_pcb(_basic_placed_circuit())
    assert '"F.Cu"' in out
    assert '"B.Cu"' in out
    assert '"Edge.Cuts"' in out


def test_kicad_pcb_net_table():
    out = export_kicad_pcb(_basic_placed_circuit())
    assert '(net 0 "")' in out
    # DRIVE, GND, LED_K, VCC ordered alphabetically → indexes 1..4
    for n in ("DRIVE", "GND", "LED_K", "VCC"):
        assert f'"{n}"' in out


def test_kicad_pcb_emits_footprints():
    out = export_kicad_pcb(_basic_placed_circuit())
    # Cada componente con footprint instancia un (footprint ...) bloque.
    fp_count = out.count("(footprint ")
    assert fp_count == 4  # 4 componentes placed


def test_kicad_pcb_emits_segments():
    out = export_kicad_pcb(_basic_placed_circuit())
    assert "(segment " in out


def test_kicad_pcb_emits_vias():
    out = export_kicad_pcb(_basic_placed_circuit())
    assert "(via " in out


def test_kicad_pcb_edge_cuts_rectangle():
    out = export_kicad_pcb(_basic_placed_circuit())
    # 4 gr_line en Edge.Cuts.
    assert out.count('(layer "Edge.Cuts")') == 4


def test_kicad_pcb_smd_uses_smd_pad_kind():
    """ESP32 está marcado SMD → pads smd."""
    c = Circuit(
        components=[_placed("U1", "esp32", 50, 40)],
        nets=[Net(name="VCC", nodes=[Node(ref="U1", pin="VCC")])],
        board=Board(width_mm=100, height_mm=80),
    )
    out = export_kicad_pcb(c)
    assert " smd " in out


def test_kicad_pcb_tht_uses_thru_hole():
    """Resistor THT → thru_hole."""
    c = Circuit(
        components=[_placed("R1", "resistor", 50, 40)],
        nets=[],
        board=Board(width_mm=100, height_mm=80),
    )
    out = export_kicad_pcb(c)
    assert " thru_hole " in out


def test_kicad_pcb_deterministic():
    c = _basic_placed_circuit()
    a = export_kicad_pcb(c)
    b = export_kicad_pcb(c)
    assert a == b
