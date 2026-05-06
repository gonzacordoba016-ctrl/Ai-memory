"""Tests for tools.eda.router — preserves routing semantics."""

import pytest

from tools.eda.router import (
    route_orthogonal,
    route_traces,
    compute_pcb_routing,
    trace_color,
)


# ── route_orthogonal ────────────────────────────────────────────────────────

def test_orthogonal_returns_four_points():
    path = route_orthogonal((0, 0), (100, 50))
    assert len(path) == 4
    assert path[0] == (0, 0)
    assert path[-1] == (100, 50)


def test_orthogonal_uses_midpoint_x():
    path = route_orthogonal((10, 20), (110, 70))
    assert path[1] == (60, 20)
    assert path[2] == (60, 70)


def test_orthogonal_zero_length():
    assert route_orthogonal((50, 50), (50, 50)) == [(50, 50), (50, 50), (50, 50), (50, 50)]


# ── route_traces ────────────────────────────────────────────────────────────

def _net(name, nodes):
    return {"name": name, "nodes": nodes}


def test_route_traces_gnd_is_thick_bottom():
    pos = {"U1": (0.0, 0.0), "U2": (10.0, 5.0)}
    traces = route_traces([_net("GND", ["U1.1", "U2.1"])], pos)
    assert all(t["net"] == "GND" for t in traces)
    # GND uses 1.0mm; primary layer is bottom.
    assert all(t["width"] == 1.0 for t in traces)
    layers = {t["layer"] for t in traces}
    assert "bottom" in layers


def test_route_traces_vcc_is_medium_bottom():
    pos = {"U1": (0.0, 0.0), "U2": (10.0, 5.0)}
    traces = route_traces([_net("VCC", ["U1.1", "U2.1"])], pos)
    assert all(t["width"] == 0.5 for t in traces)


def test_route_traces_i2c_is_top_thin():
    pos = {"U1": (0.0, 0.0), "U2": (10.0, 5.0)}
    traces = route_traces([_net("SDA", ["U1.1", "U2.1"])], pos)
    assert all(t["width"] == 0.3 for t in traces)
    assert any(t["layer"] == "top" for t in traces)


def test_route_traces_default_signal():
    pos = {"U1": (0.0, 0.0), "U2": (10.0, 5.0)}
    traces = route_traces([_net("DATA1", ["U1.1", "U2.1"])], pos)
    assert all(t["width"] == 0.25 for t in traces)


def test_route_traces_skips_zero_length_segments():
    # Same x and same y → all 3 candidate segments are zero length and dropped.
    pos = {"U1": (5.0, 5.0), "U2": (5.0, 5.0)}
    traces = route_traces([_net("SIG", ["U1.1", "U2.1"])], pos)
    assert traces == []


def test_route_traces_pure_horizontal():
    # Same y, different x → vertical segment is zero length and dropped.
    pos = {"U1": (0.0, 5.0), "U2": (10.0, 5.0)}
    traces = route_traces([_net("SIG", ["U1.1", "U2.1"])], pos)
    assert all(abs(t["y1"] - t["y2"]) < 0.001 for t in traces)
    assert len(traces) == 2  # left half + right half, no vertical


def test_route_traces_pure_vertical():
    # Same x, different y → both horizontal segments are zero length.
    pos = {"U1": (5.0, 0.0), "U2": (5.0, 10.0)}
    traces = route_traces([_net("SIG", ["U1.1", "U2.1"])], pos)
    assert len(traces) == 1
    assert abs(traces[0]["x1"] - traces[0]["x2"]) < 0.001


def test_route_traces_skips_unknown_node():
    pos = {"U1": (0.0, 0.0)}
    traces = route_traces([_net("SIG", ["U1.1", "MISSING.1"])], pos)
    assert traces == []  # only 1 valid coord, no segment


def test_route_traces_chains_multiple_nodes():
    pos = {"U1": (0.0, 0.0), "U2": (10.0, 5.0), "U3": (20.0, 10.0)}
    traces = route_traces([_net("SIG", ["U1.1", "U2.1", "U3.1"])], pos)
    # Two segments per pair, skipping zero-length; 3 nodes -> 2 pairs -> up to 6 segs
    assert len(traces) > 0


def test_compute_pcb_routing_delegates():
    pos = {"U1": (0.0, 0.0), "U2": (10.0, 5.0)}
    nets = [_net("GND", ["U1.1", "U2.1"])]
    out_a = compute_pcb_routing([], nets, pos, {})
    out_b = route_traces(nets, pos)
    assert out_a == out_b


# ── trace_color ─────────────────────────────────────────────────────────────

def test_trace_color_gnd():
    assert trace_color("top", "GND") == "#b87333"
    assert trace_color("bottom", "GROUND") == "#b87333"


def test_trace_color_vcc_layer_dependent():
    assert trace_color("top", "VCC") == "#cc3333"
    assert trace_color("bottom", "VCC") == "#b87333"


def test_trace_color_signal_layer_dependent():
    assert trace_color("top", "DATA") == "#daa520"
    assert trace_color("bottom", "DATA") == "#c09030"
