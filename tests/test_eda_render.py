"""Tests de los renderers puros — schematic + PCB."""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

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
from tools.eda.placement_engine import place
from tools.eda.render import (
    PCBRenderOptions,
    SchematicRenderOptions,
    render_pcb_svg,
    render_schematic_svg,
)
from tools.eda.routing_engine import route


SVG_NS = "http://www.w3.org/2000/svg"


def _parse(svg: str) -> ET.Element:
    """Parsea SVG → ElementTree root. Falla si XML inválido."""
    # Strip XML declaration si está, ET la maneja igual.
    return ET.fromstring(svg)


def _placed(ref, type_, x, y) -> Component:
    return Component(
        ref=ref, type=type_,
        placement=PlacementInfo(position=Vec2(x=x, y=y)),
    )


def _basic_placed_circuit() -> Circuit:
    return Circuit(
        components=[
            _placed("U1", "esp32", 50.0, 40.0),
            _placed("S1", "dht22", 20.0, 40.0),
            _placed("R1", "resistor", 30.0, 70.0),
        ],
        nets=[
            Net(name="DATA", nodes=[Node(ref="U1", pin="GPIO16"),
                                     Node(ref="S1", pin="DATA"),
                                     Node(ref="R1", pin="1")]),
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC"),
                                    Node(ref="S1", pin="VCC")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND"),
                                    Node(ref="S1", pin="GND"),
                                    Node(ref="R1", pin="2")]),
        ],
        board=Board(width_mm=120.0, height_mm=100.0),
    )


# ─── Schematic renderer ───────────────────────────────────────────────────


def test_schematic_renders_valid_xml():
    svg = render_schematic_svg(_basic_placed_circuit())
    root = _parse(svg)
    assert root.tag == f"{{{SVG_NS}}}svg"


def test_schematic_has_all_components():
    svg = render_schematic_svg(_basic_placed_circuit())
    root = _parse(svg)
    refs = [g.attrib.get("data-ref") for g in root.iter(f"{{{SVG_NS}}}g")
            if g.attrib.get("class") == "component"]
    assert sorted(refs) == ["R1", "S1", "U1"]


def test_schematic_skips_components_without_placement():
    c = Circuit(
        components=[_placed("U1", "esp32", 50, 40),
                    Component(ref="X1", type="resistor")],
        nets=[],
        board=Board(width_mm=100, height_mm=80),
    )
    svg = render_schematic_svg(c)
    root = _parse(svg)
    refs = [g.attrib.get("data-ref") for g in root.iter(f"{{{SVG_NS}}}g")
            if g.attrib.get("class") == "component"]
    assert refs == ["U1"]


def test_schematic_emits_wires_for_multinode_nets():
    svg = render_schematic_svg(_basic_placed_circuit())
    root = _parse(svg)
    wires = [p for p in root.iter(f"{{{SVG_NS}}}polyline")
             if p.attrib.get("class") == "wire"]
    # 3 nets con 2-3 nodos cada una: DATA(3)+VCC(2)+GND(3) = 8 wires.
    assert len(wires) == 8


def test_schematic_skips_singleton_nets():
    c = Circuit(
        components=[_placed("U1", "esp32", 50, 40)],
        nets=[Net(name="VCC", nodes=[Node(ref="U1", pin="VCC")])],
        board=Board(width_mm=100, height_mm=80),
    )
    svg = render_schematic_svg(c)
    root = _parse(svg)
    wires = [p for p in root.iter(f"{{{SVG_NS}}}polyline")
             if p.attrib.get("class") == "wire"]
    assert wires == []


def test_schematic_emits_junctions_for_3plus_node_nets():
    svg = render_schematic_svg(_basic_placed_circuit())
    root = _parse(svg)
    junctions = [c for c in root.iter(f"{{{SVG_NS}}}circle")
                 if c.attrib.get("class") == "junction"]
    # DATA y GND tienen 3 nodos cada una → 2 junctions.
    assert len(junctions) == 2


def test_schematic_emits_net_labels():
    svg = render_schematic_svg(_basic_placed_circuit())
    root = _parse(svg)
    labels = [t.text for t in root.iter(f"{{{SVG_NS}}}text")
              if t.attrib.get("class") == "net-label"]
    assert "DATA" in labels
    assert "VCC" in labels
    assert "GND" in labels


def test_schematic_net_labels_can_be_disabled():
    svg = render_schematic_svg(
        _basic_placed_circuit(),
        SchematicRenderOptions(show_net_labels=False),
    )
    root = _parse(svg)
    labels = [t for t in root.iter(f"{{{SVG_NS}}}text")
              if t.attrib.get("class") == "net-label"]
    assert labels == []


def test_schematic_title_block_contains_options():
    svg = render_schematic_svg(
        _basic_placed_circuit(),
        SchematicRenderOptions(title="MY_CIRCUIT"),
    )
    assert "MY_CIRCUIT" in svg


def test_schematic_is_deterministic():
    c = _basic_placed_circuit()
    a = render_schematic_svg(c)
    b = render_schematic_svg(c)
    assert a == b


def test_schematic_uses_board_dimensions():
    svg = render_schematic_svg(_basic_placed_circuit())
    root = _parse(svg)
    assert root.attrib["viewBox"] == "0 0 120.0 100.0"


# ─── PCB renderer ─────────────────────────────────────────────────────────


def test_pcb_renders_valid_xml():
    c = _basic_placed_circuit()
    svg = render_pcb_svg(c)
    root = _parse(svg)
    assert root.tag == f"{{{SVG_NS}}}svg"


def test_pcb_requires_board():
    c = Circuit(components=[_placed("U1", "esp32", 50, 40)])
    with pytest.raises(ValueError):
        render_pcb_svg(c)


def test_pcb_emits_edge_cuts():
    c = _basic_placed_circuit()
    svg = render_pcb_svg(c)
    root = _parse(svg)
    edge_groups = [g for g in root.iter(f"{{{SVG_NS}}}g")
                   if g.attrib.get("id") == "edge-cuts"]
    assert len(edge_groups) == 1


def test_pcb_emits_footprints():
    c = _basic_placed_circuit()
    svg = render_pcb_svg(c)
    root = _parse(svg)
    fps = [g for g in root.iter(f"{{{SVG_NS}}}g")
           if g.attrib.get("class") == "footprint"]
    refs = sorted(g.attrib["data-ref"] for g in fps)
    assert refs == ["R1", "S1", "U1"]


def test_pcb_emits_traces_with_correct_layers():
    c = _basic_placed_circuit().model_copy(update={
        "traces": [
            Trace(net="DATA", points=[Vec2(x=20, y=40), Vec2(x=50, y=40)],
                  width_mm=0.25, layer=Layer.F_CU),
            Trace(net="GND", points=[Vec2(x=20, y=40), Vec2(x=30, y=70)],
                  width_mm=0.5, layer=Layer.B_CU),
        ],
    })
    svg = render_pcb_svg(c)
    root = _parse(svg)
    f_cu_traces = [p for p in root.iter(f"{{{SVG_NS}}}polyline")
                   if "layer-f-cu" in p.attrib.get("class", "")]
    b_cu_traces = [p for p in root.iter(f"{{{SVG_NS}}}polyline")
                   if "layer-b-cu" in p.attrib.get("class", "")]
    assert len(f_cu_traces) == 1
    assert len(b_cu_traces) == 1


def test_pcb_trace_width_propagated():
    c = _basic_placed_circuit().model_copy(update={
        "traces": [
            Trace(net="POWER", points=[Vec2(x=0, y=0), Vec2(x=10, y=0)],
                  width_mm=0.75, layer=Layer.F_CU),
        ],
    })
    svg = render_pcb_svg(c)
    root = _parse(svg)
    pls = [p for p in root.iter(f"{{{SVG_NS}}}polyline")
           if "trace" in p.attrib.get("class", "")]
    assert len(pls) == 1
    assert pls[0].attrib["stroke-width"] == "0.75"


def test_pcb_emits_vias():
    c = _basic_placed_circuit().model_copy(update={
        "vias": [
            Via(net="X", position=Vec2(x=30, y=40),
                drill_mm=0.4, diameter_mm=0.8),
        ],
    })
    svg = render_pcb_svg(c)
    root = _parse(svg)
    vias = [el for el in root.iter(f"{{{SVG_NS}}}circle")
            if el.attrib.get("class") == "via"]
    drills = [el for el in root.iter(f"{{{SVG_NS}}}circle")
              if el.attrib.get("class") == "via-drill"]
    assert len(vias) == 1
    assert len(drills) == 1


def test_pcb_is_deterministic():
    c = _basic_placed_circuit().model_copy(update={
        "traces": [
            Trace(net="A", points=[Vec2(x=0, y=0), Vec2(x=10, y=0)],
                  width_mm=0.25, layer=Layer.F_CU),
        ],
    })
    a = render_pcb_svg(c)
    b = render_pcb_svg(c)
    assert a == b


def test_pcb_courtyards_can_be_disabled():
    c = _basic_placed_circuit()
    svg_with = render_pcb_svg(c, PCBRenderOptions(show_courtyards=True))
    svg_without = render_pcb_svg(c, PCBRenderOptions(show_courtyards=False))
    root_with = _parse(svg_with)
    root_without = _parse(svg_without)
    n_with = len([r for r in root_with.iter(f"{{{SVG_NS}}}rect")
                  if r.attrib.get("class") == "courtyard"])
    n_without = len([r for r in root_without.iter(f"{{{SVG_NS}}}rect")
                     if r.attrib.get("class") == "courtyard"])
    assert n_with > 0
    assert n_without == 0


# ─── Pipeline integrado: place → route → render ───────────────────────────


def test_full_pipeline_produces_valid_svgs():
    """End-to-end: IR sin coords → place → route → render → SVG válido."""
    raw = Circuit(
        components=[
            Component(ref="U1", type="esp32"),
            Component(ref="S1", type="dht22"),
            Component(ref="R1", type="resistor"),
            Component(ref="LED1", type="led"),
        ],
        nets=[
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC"),
                                    Node(ref="S1", pin="VCC")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND"),
                                    Node(ref="S1", pin="GND"),
                                    Node(ref="LED1", pin="cathode")]),
            Net(name="DATA", nodes=[Node(ref="U1", pin="GPIO16"),
                                     Node(ref="S1", pin="DATA")]),
            Net(name="LED_DRIVE", nodes=[Node(ref="U1", pin="GPIO2"),
                                          Node(ref="R1", pin="1")]),
            Net(name="LED_K", nodes=[Node(ref="R1", pin="2"),
                                      Node(ref="LED1", pin="anode")]),
        ],
    )
    placed = place(raw).circuit
    routed = route(placed).circuit

    sch_svg = render_schematic_svg(routed)
    pcb_svg = render_pcb_svg(routed)

    _parse(sch_svg)
    _parse(pcb_svg)

    # Ambos contienen los 4 componentes.
    for ref in ("U1", "S1", "R1", "LED1"):
        assert ref in sch_svg
        assert ref in pcb_svg
