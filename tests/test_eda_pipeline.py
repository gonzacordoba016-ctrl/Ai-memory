"""Tests del wrapper end-to-end."""
from __future__ import annotations

from tools.eda.ir import Circuit, Component, Net, Node
from tools.eda.pipeline import (
    PipelineOptions,
    PipelineResult,
    run_pipeline,
)


def _basic() -> Circuit:
    return Circuit(
        components=[
            Component(ref="U1", type="esp32"),
            Component(ref="R1", type="resistor", value="220"),
            Component(ref="LED1", type="led"),
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
    )


def test_pipeline_runs_end_to_end():
    out = run_pipeline(_basic())
    assert isinstance(out, PipelineResult)
    assert out.schematic_svg
    assert out.pcb_svg
    assert out.kicad_sch
    assert out.kicad_pcb
    assert out.bom_csv


def test_pipeline_assigns_placements():
    out = run_pipeline(_basic())
    for c in out.circuit.components:
        assert c.placement is not None


def test_pipeline_generates_traces():
    out = run_pipeline(_basic())
    assert len(out.circuit.traces) > 0


def test_pipeline_skip_render():
    out = run_pipeline(_basic(), PipelineOptions(
        do_render_schematic=False,
        do_render_pcb=False,
        do_export_kicad_sch=False,
        do_export_kicad_pcb=False,
        do_export_bom=False,
    ))
    assert out.schematic_svg == ""
    assert out.pcb_svg == ""
    assert out.kicad_sch == ""
    assert out.kicad_pcb == ""
    assert out.bom_csv == ""


def test_pipeline_pre_drc_catches_issues():
    """ESP32 sin GND → MCU_MISSING_GND en pre DRC."""
    c = Circuit(
        components=[Component(ref="U1", type="esp32")],
        nets=[Net(name="VCC", nodes=[Node(ref="U1", pin="VCC")])],
    )
    out = run_pipeline(c)
    pre_codes = {i.code for i in out.drc_pre}
    assert "MCU_MISSING_GND" in pre_codes


def test_pipeline_deterministic():
    a = run_pipeline(_basic())
    b = run_pipeline(_basic())
    assert a.schematic_svg == b.schematic_svg
    assert a.pcb_svg == b.pcb_svg
    assert a.kicad_sch == b.kicad_sch
    assert a.kicad_pcb == b.kicad_pcb
    assert a.bom_csv == b.bom_csv


def test_pipeline_has_errors_property():
    c = Circuit(
        components=[Component(ref="U1", type="esp32")],
        nets=[Net(name="VCC", nodes=[Node(ref="U1", pin="VCC")])],
    )
    out = run_pipeline(c)
    assert out.has_errors()  # MCU_MISSING_GND es error
