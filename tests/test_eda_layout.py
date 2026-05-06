"""Tests for tools.eda.layout — preserves layout semantics from schematic_renderer."""

import pytest

from tools.design_rules import get_sheet_size
from tools.eda.layout import (
    build_relay_groups,
    layout_components,
    compute_schematic_layout,
    validate_positions,
    PX_PER_MM,
)


# ── build_relay_groups ──────────────────────────────────────────────────────

def test_relay_groups_pair_diode_and_resistor():
    comps = [
        {"id": "RL1", "type": "relay"},
        {"id": "D_fly1", "type": "diode"},
        {"id": "R1", "type": "resistor"},
    ]
    groups = build_relay_groups(comps)
    assert "RL1" in groups
    cell = groups["RL1"]
    assert [c["id"] for c in cell] == ["RL1", "D_fly1", "R1"]


def test_relay_groups_handles_relay_without_extras():
    comps = [{"id": "RL1", "type": "relay"}]
    groups = build_relay_groups(comps)
    assert groups["RL1"] == [comps[0]]


def test_relay_groups_finds_diode_with_fly_pattern():
    comps = [
        {"id": "RL2", "type": "relay"},
        {"id": "D_flyback_RL2", "type": "diode"},
    ]
    groups = build_relay_groups(comps)
    # Should match D_flyback_RL2 via the candidate list
    cell = groups["RL2"]
    assert any(c["id"] == "D_flyback_RL2" for c in cell)


def test_relay_groups_no_relays():
    comps = [{"id": "U1", "type": "esp32"}, {"id": "R1", "type": "resistor"}]
    assert build_relay_groups(comps) == {}


def test_relay_groups_id_prefix_rl():
    # Components whose id starts with rl/RL are treated as relays even if type isn't relay.
    comps = [{"id": "rl5", "type": "generic"}]
    groups = build_relay_groups(comps)
    assert "rl5" in groups


# ── layout_components ───────────────────────────────────────────────────────

def test_layout_assigns_distinct_x_for_each_zone():
    comps = [
        {"id": "U1", "type": "esp32"},          # mcu
        {"id": "S1", "type": "bmp280"},         # sensor
        {"id": "RL1", "type": "relay"},         # relay
        {"id": "J1", "type": "connector"},      # output
    ]
    pos = layout_components(comps, width=1200, height=600, saved={})
    xs = {pos[c["id"]][0] for c in comps}
    # Different zones must have different X centers
    assert len(xs) == 4


def test_layout_honors_saved_positions():
    comps = [{"id": "U1", "type": "esp32"}, {"id": "U2", "type": "esp32"}]
    saved = {"U1": {"x": 123, "y": 456}}
    pos = layout_components(comps, width=1200, height=600, saved=saved)
    assert pos["U1"] == (123, 456)
    assert "U2" in pos


def test_layout_relay_cell_places_diode_and_resistor_relative():
    comps = [
        {"id": "RL1", "type": "relay"},
        {"id": "D_fly1", "type": "diode"},
        {"id": "R1", "type": "resistor"},
    ]
    pos = layout_components(comps, width=1200, height=600, saved={})
    rx, ry = pos["RL1"]
    dx, dy = pos["D_fly1"]
    rrx, rry = pos["R1"]
    assert dx == rx - 75
    assert dy == ry - 18
    assert rrx == rx - 140
    assert rry == ry


def test_layout_empty_components():
    assert layout_components([], 1000, 600, {}) == {}


def test_layout_multiple_components_same_zone_different_y():
    comps = [
        {"id": "U1", "type": "esp32"},
        {"id": "U2", "type": "esp32"},
        {"id": "U3", "type": "esp32"},
    ]
    pos = layout_components(comps, 1200, 600, {})
    ys = {pos[c["id"]][1] for c in comps}
    assert len(ys) == 3  # all different Y


# ── compute_schematic_layout ────────────────────────────────────────────────

def test_compute_layout_grid_snaps_positions():
    comps = [{"id": "U1", "type": "esp32"}]
    sheet = get_sheet_size(1)
    pos = compute_schematic_layout(comps, [], sheet)
    grid_px = sheet["grid"] * PX_PER_MM
    x, y = pos["U1"]
    # Snapped values are integer multiples of grid (within float precision).
    assert abs((x / grid_px) - round(x / grid_px)) < 1e-6
    assert abs((y / grid_px) - round(y / grid_px)) < 1e-6


def test_compute_layout_returns_position_for_every_component():
    comps = [
        {"id": "U1", "type": "esp32"},
        {"id": "S1", "type": "bmp280"},
        {"id": "RL1", "type": "relay"},
    ]
    sheet = get_sheet_size(len(comps))
    pos = compute_schematic_layout(comps, [], sheet)
    assert set(pos.keys()) == {"U1", "S1", "RL1"}


# ── validate_positions ──────────────────────────────────────────────────────

def test_validate_clamps_out_of_bounds():
    sheet = get_sheet_size(1)
    bad = {"U1": (-9999, -9999), "U2": (99999, 99999)}
    out = validate_positions(bad, sheet)
    x_min = 10.0 * PX_PER_MM  # MARGIN_MM=10
    x_max = (sheet["w"] - 10.0) * PX_PER_MM
    grid_px = sheet["grid"] * PX_PER_MM
    # Clamp + grid-snap can land up to one grid step beyond the raw bound.
    assert x_min - grid_px <= out["U1"][0] <= x_max + grid_px
    assert x_min - grid_px <= out["U2"][0] <= x_max + grid_px
    # Sanity: out-of-bounds values are at least pulled into the broad sheet area.
    assert 0 <= out["U1"][0] < sheet["w"] * PX_PER_MM
    assert 0 <= out["U2"][0] < sheet["w"] * PX_PER_MM


def test_validate_nudges_overlapping_positions():
    sheet = get_sheet_size(2)
    same = {"U1": (200.0, 200.0), "U2": (200.0, 200.0)}
    out = validate_positions(same, sheet)
    # min_sep = 15mm * 4px/mm = 60px; second one should be nudged below
    assert out["U2"][1] > out["U1"][1]


def test_validate_preserves_in_bounds_positions():
    sheet = get_sheet_size(2)
    grid_px = sheet["grid"] * PX_PER_MM
    # Pre-snapped, well-separated positions
    fine = {"U1": (100 * grid_px, 50 * grid_px), "U2": (10 * grid_px, 10 * grid_px)}
    out = validate_positions(fine, sheet)
    assert out["U1"] == fine["U1"]
    assert out["U2"] == fine["U2"]
