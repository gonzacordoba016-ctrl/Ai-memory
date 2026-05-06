"""Schematic layout — assigns x,y positions to each component by zone.

Ported verbatim from schematic_renderer (_layout_components, _compute_positions,
_validate_positions, _build_relay_groups). Behavior is byte-equivalent.
"""

import math
from typing import Dict, List, Optional, Tuple

from tools.component_types import _MCU_TYPES, _RELAY_TYPES
from tools.design_rules import MARGIN_MM, TITLE_BLOCK_H, snap_to_grid
from tools.eda.classifier import classify_zone


PX_PER_MM = 4.0  # 1mm = 4 SVG user units (pixel scale)


def build_relay_groups(components: List[Dict]) -> Dict[str, List[Dict]]:
    """For each relay RLn, find its associated flyback diode and control resistor.

    Returns {relay_id: [relay_comp, diode_comp?, resistor_comp?]}.
    Components in a relay group are not placed independently.
    """
    by_id = {c["id"]: c for c in components}
    relay_ids = [
        c["id"] for c in components
        if (c.get("resolved_type") or c.get("type") or "").lower() in _RELAY_TYPES
        or c["id"].lower().startswith("rl")
    ]

    groups: Dict[str, List[Dict]] = {}
    used_ids: set = set()

    for rid in relay_ids:
        if rid in used_ids:
            continue
        relay = by_id[rid]
        cell = [relay]
        used_ids.add(rid)

        n_match = "".join(ch for ch in rid if ch.isdigit())
        rid_lo = rid.lower()
        candidates_d = []
        if n_match:
            candidates_d += [
                f"D_fly{n_match}", f"D_fly_{rid}", f"D_fly_{rid_lo}",
                f"D{n_match}", f"D_flyback_{rid}", f"Dfly{n_match}",
                f"d_fly{n_match}", f"d{n_match}",
            ]
        for cid2, comp2 in by_id.items():
            cid2_lo = cid2.lower()
            t2 = (comp2.get("resolved_type") or comp2.get("type") or "").lower()
            if t2 in ("diode", "1n4007", "1n5819", "1n4148") and \
               "fly" in cid2_lo and n_match and n_match in cid2_lo and \
               cid2 not in used_ids:
                candidates_d.append(cid2)
        for cid2 in candidates_d:
            if cid2 in by_id and cid2 not in used_ids:
                cell.append(by_id[cid2])
                used_ids.add(cid2)
                break

        candidates_r = []
        if n_match:
            candidates_r += [f"R{n_match}", f"R_ctrl_{rid}", f"Rctrl{n_match}",
                             f"R_{rid}", f"r{n_match}"]
        for cid2 in candidates_r:
            if cid2 in by_id and cid2 not in used_ids:
                cell.append(by_id[cid2])
                used_ids.add(cid2)
                break

        groups[rid] = cell

    return groups


def layout_components(components: List[Dict], width: int, height: int,
                      saved: Dict[str, Dict],
                      nets: Optional[List[Dict]] = None) -> Dict[str, Tuple[int, int]]:
    """Zone-based layout left-to-right: AC | Power+MCU | Sensor | Other | Relay | Output.

    With `nets`, runs 3 iterations of barycentric Y-reorder per zone to minimize
    wire crossings.
    """
    positions: Dict[str, Tuple[int, int]] = {}

    for comp_id, pos in saved.items():
        if isinstance(pos, dict) and "x" in pos and "y" in pos:
            positions[comp_id] = (int(pos["x"]), int(pos["y"]))

    pending = [c for c in components if c["id"] not in positions]
    if not pending:
        return positions

    relay_groups = build_relay_groups(pending)
    grouped_ids: set = {cid for cell in relay_groups.values() for cid in (c["id"] for c in cell)}

    zones: Dict[str, List[Dict]] = {z: [] for z in ("ac", "mcu", "sensor", "relay", "output", "other")}
    for comp in pending:
        if comp["id"] in grouped_ids:
            continue
        zones[classify_zone(comp)].append(comp)
    for rid in relay_groups:
        pass

    x_margin = 80
    SLOT_AC     = 240
    SLOT_MCU    = 240
    SLOT_SENSOR = 220
    SLOT_OTHER  = 200
    SLOT_RELAY  = 360
    SLOT_OUTPUT = 200
    GAP         = 60

    mcu_sorted = sorted(
        zones["mcu"],
        key=lambda c: 0 if (c.get("resolved_type") or c.get("type") or "").lower() in _MCU_TYPES else 1,
    )
    has_ac      = bool(zones["ac"])
    has_mcu     = bool(mcu_sorted)
    has_sensor  = bool(zones["sensor"])
    has_other   = bool([c for c in zones["other"] if c["id"] not in positions])
    has_relay   = bool(relay_groups)
    has_output  = bool(zones["output"])

    cur = x_margin
    if has_ac:
        x_ac_c = cur + SLOT_AC // 2; cur += SLOT_AC + GAP
    else:
        x_ac_c = cur

    if has_mcu:
        x_mcu_c = cur + SLOT_MCU // 2; cur += SLOT_MCU + GAP
    else:
        x_mcu_c = cur

    if has_sensor:
        x_sensor_c = cur + SLOT_SENSOR // 2; cur += SLOT_SENSOR + GAP
    else:
        x_sensor_c = cur

    if has_other:
        x_other_c = cur + SLOT_OTHER // 2; cur += SLOT_OTHER + GAP
    else:
        x_other_c = cur

    if has_relay:
        x_relay_c = cur + SLOT_RELAY // 2; cur += SLOT_RELAY + GAP
    else:
        x_relay_c = cur

    if has_output:
        x_output_c = cur + SLOT_OUTPUT // 2; cur += SLOT_OUTPUT
    else:
        x_output_c = cur

    y_top    = 90
    y_bottom = max(y_top + 200, height - 40)
    y_height = y_bottom - y_top

    def _stack_y_positions(n: int) -> List[int]:
        if n == 0:
            return []
        if n == 1:
            return [y_top + y_height // 2]
        spacing = max(60, y_height // n)
        total = (n - 1) * spacing
        start = y_top + (y_height - total) // 2
        return [start + i * spacing for i in range(n)]

    ac_comps = zones["ac"]
    for comp, ypos in zip(ac_comps, _stack_y_positions(len(ac_comps))):
        positions[comp["id"]] = (x_ac_c, ypos)

    for comp, ypos in zip(mcu_sorted, _stack_y_positions(len(mcu_sorted))):
        positions[comp["id"]] = (x_mcu_c, ypos)

    relay_cells = list(relay_groups.values())
    n_cells = len(relay_cells)
    if n_cells > 0:
        cell_height = max(120, min(180, y_height // max(n_cells, 1)))
        cell_y_positions = _stack_y_positions(n_cells)
        for cell, cy_center in zip(relay_cells, cell_y_positions):
            relay = cell[0]
            positions[relay["id"]] = (x_relay_c, cy_center)
            if len(cell) > 1:
                positions[cell[1]["id"]] = (x_relay_c - 75, cy_center - 18)
            if len(cell) > 2:
                positions[cell[2]["id"]] = (x_relay_c - 140, cy_center)

    standalone_relays = [c for c in zones["relay"] if c["id"] not in positions]
    if standalone_relays:
        sr_y = _stack_y_positions(len(standalone_relays))
        for comp, ypos in zip(standalone_relays, sr_y):
            positions[comp["id"]] = (x_relay_c, ypos)

    out_comps = zones["output"]
    for comp, ypos in zip(out_comps, _stack_y_positions(len(out_comps))):
        positions[comp["id"]] = (x_output_c, ypos)

    sensor_comps = [c for c in zones["sensor"] if c["id"] not in positions]
    if sensor_comps:
        for comp, ypos in zip(sensor_comps, _stack_y_positions(len(sensor_comps))):
            positions[comp["id"]] = (x_sensor_c, ypos)

    other_comps = [c for c in zones["other"] if c["id"] not in positions]
    other_col2_ids: set = set()
    x_other_col2: int = x_other_c + SLOT_OTHER + GAP
    if other_comps:
        active_zone_count = sum(
            1 for v in (has_ac, has_mcu, has_sensor, has_relay, has_output) if v
        )
        if active_zone_count < 3 and len(other_comps) >= 2:
            other_col1 = other_comps[::2]
            other_col2 = other_comps[1::2]
            other_col2_ids = {c["id"] for c in other_col2}
            for comp, ypos in zip(other_col1, _stack_y_positions(len(other_col1))):
                positions[comp["id"]] = (x_other_c, ypos)
            for comp, ypos in zip(other_col2, _stack_y_positions(len(other_col2))):
                positions[comp["id"]] = (x_other_col2, ypos)
        else:
            for comp, ypos in zip(other_comps, _stack_y_positions(len(other_comps))):
                positions[comp["id"]] = (x_other_c, ypos)

    if nets:
        adj: Dict[str, set] = {c["id"]: set() for c in pending}
        for net in nets:
            ids_in_net = [str(node).split(".")[0] for node in net.get("nodes", [])]
            ids_in_net = [i for i in ids_in_net if i in adj]
            for i in ids_in_net:
                for j in ids_in_net:
                    if i != j:
                        adj[i].add(j)

        comp_zone: Dict[str, str] = {}
        for z, lst in zones.items():
            for c in lst:
                comp_zone[c["id"]] = z
        for cell in relay_groups.values():
            for c in cell:
                comp_zone[c["id"]] = "relay"

        zone_pop = {z: len(lst) for z, lst in zones.items()}
        zone_pop["relay"] = max(zone_pop["relay"], len(relay_groups))
        anchor = max(zone_pop, key=lambda z: zone_pop[z])

        def _reorder_zone(zone_name: str, zone_comps: List[Dict], x_center: int) -> None:
            if zone_name == anchor or len(zone_comps) < 2:
                return
            targets: List[Tuple[float, Dict]] = []
            for c in zone_comps:
                ys = [positions[nb][1] for nb in adj.get(c["id"], ())
                       if nb in positions and comp_zone.get(nb) != zone_name]
                if ys:
                    targets.append((sum(ys) / len(ys), c))
                else:
                    targets.append((float(positions[c["id"]][1]), c))
            targets.sort(key=lambda t: t[0])
            reordered = [t[1] for t in targets]
            for c, y in zip(reordered, _stack_y_positions(len(reordered))):
                positions[c["id"]] = (x_center, y)

        for _ in range(3):
            _reorder_zone("ac",      ac_comps,      x_ac_c)
            _reorder_zone("mcu",     mcu_sorted,    x_mcu_c)
            _reorder_zone("sensor",  sensor_comps,  x_sensor_c)
            _reorder_zone("other",   other_comps,   x_other_c)
            _reorder_zone("output",  out_comps,     x_output_c)
            if anchor != "relay" and len(relay_groups) >= 2:
                relay_targets: List[Tuple[float, List[Dict]]] = []
                for cell in relay_cells:
                    relay = cell[0]
                    ys = [positions[nb][1] for nb in adj.get(relay["id"], ())
                           if nb in positions and comp_zone.get(nb) != "relay"]
                    relay_targets.append((sum(ys) / len(ys) if ys else float(positions[relay["id"]][1]), cell))
                relay_targets.sort(key=lambda t: t[0])
                reordered_cells = [t[1] for t in relay_targets]
                new_cy = _stack_y_positions(len(reordered_cells))
                for cell, cy in zip(reordered_cells, new_cy):
                    relay = cell[0]
                    positions[relay["id"]] = (x_relay_c, cy)
                    if len(cell) > 1:
                        positions[cell[1]["id"]] = (x_relay_c - 75, cy - 18)
                    if len(cell) > 2:
                        positions[cell[2]["id"]] = (x_relay_c - 140, cy)

    if other_col2_ids:
        for cid in other_col2_ids:
            if cid in positions:
                _, y = positions[cid]
                positions[cid] = (x_other_col2, y)

    return positions


def compute_schematic_layout(
    components: List[Dict], nets: List[Dict], sheet: Dict
) -> Dict[str, Tuple[float, float]]:
    """Returns {comp_id: (x, y)} grid-snapped positions in SVG px.

    Canvas size is derived from active zones (never smaller than sheet * PX_PER_MM).
    Zone order follows design_rules.ZONE_ORDER.
    """
    n_ac     = sum(1 for c in components if classify_zone(c) == "ac")
    n_mcu    = sum(1 for c in components if classify_zone(c) == "mcu")
    n_sensor = sum(1 for c in components if classify_zone(c) == "sensor")
    n_other  = sum(1 for c in components if classify_zone(c) == "other")
    n_relay  = sum(1 for c in components
                   if (c.get("resolved_type") or c.get("type") or "").lower()
                   in ("relay", "relay_module", "ssr") or c.get("id", "").lower().startswith("rl"))
    n_output = sum(1 for c in components if classify_zone(c) == "output")
    active   = sum(1 for v in (n_ac, n_mcu, n_sensor, n_other, n_relay, n_output) if v > 0)

    slots_w = (240 * bool(n_ac) + 240 * bool(n_mcu) + 220 * bool(n_sensor)
               + 200 * bool(n_other) + 360 * bool(n_relay) + 200 * bool(n_output))
    gap_w   = 60 * max(0, active - 1)
    w_px    = max(int(sheet["w"] * PX_PER_MM), slots_w + gap_w + 160)

    active_excl_other = sum(1 for v in (n_ac, n_mcu, n_sensor, n_relay, n_output) if v > 0)
    n_other_eff = (math.ceil(n_other / 2)
                   if active_excl_other < 3 and n_other >= 2 else n_other)
    n_max_zone  = max(n_ac, n_mcu, n_sensor, n_other_eff, n_relay, n_output, 1)
    h_px        = max(int(sheet["h"] * PX_PER_MM), n_max_zone * 110 + 180)

    grid_px = sheet["grid"] * PX_PER_MM
    raw = layout_components(components, w_px, h_px - 90, {}, nets)
    return {cid: snap_to_grid(x, y, grid_px) for cid, (x, y) in raw.items()}


def validate_positions(
    positions: Dict[str, Tuple[float, float]], sheet: Dict
) -> Dict[str, Tuple[float, float]]:
    """Clamps out-of-bounds positions to usable area and nudges overlaps < 15mm."""
    x_min   = MARGIN_MM * PX_PER_MM
    x_max   = (sheet["w"] - MARGIN_MM) * PX_PER_MM
    y_min   = MARGIN_MM * PX_PER_MM
    y_max   = (sheet["h"] - TITLE_BLOCK_H - MARGIN_MM) * PX_PER_MM
    grid_px = sheet["grid"] * PX_PER_MM
    min_sep = 15.0 * PX_PER_MM

    result: Dict[str, Tuple[float, float]] = {}
    for cid, (x, y) in positions.items():
        result[cid] = snap_to_grid(
            max(x_min, min(x_max, x)),
            max(y_min, min(y_max, y)),
            grid_px,
        )

    ids = list(result.keys())
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            ax, ay = result[a]
            bx, by = result[b]
            if abs(ax - bx) < min_sep and abs(ay - by) < min_sep:
                result[b] = snap_to_grid(bx, min(by + min_sep, y_max), grid_px)

    return result
