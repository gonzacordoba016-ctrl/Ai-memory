"""Schematic SVG drawing — owns the SchematicRenderer class.

Ported verbatim from schematic_renderer.py (the class body, lines 519-1849).
Helpers (classify, layout, route) are imported from sibling eda modules and
re-bound to the underscore-prefixed names the class body uses, so the moved
code needs zero internal changes. Behavior is byte-equivalent.
"""

import math
from typing import Any, Dict, List, Optional, Tuple

import svgwrite

from core.logger import get_logger
from tools.kicad_sym_renderer import KiCadSymRenderer as _KSR
from tools.design_rules import (
    get_sheet_size,
    snap_to_grid,
    BORDER_MM,
    ZONE_REF_MM,
    TITLE_BLOCK_W_MM,
    TITLE_BLOCK_H_MM,
    ZONE_COLS,
    ZONE_ROWS,
)

from tools.eda.classifier import classify_zone as _classify_zone
from tools.eda.layout import (
    PX_PER_MM as _PX_PER_MM,
    compute_schematic_layout as _compute_positions,
    validate_positions as _validate_positions,
    drawing_area_px as _drawing_area_px,
)
from tools.eda.router import route_orthogonal as _route_orthogonal


_kicad = _KSR()
logger = get_logger(__name__)


def _net_color(net_name: str) -> str:
    name = net_name.lower()
    if any(v in name for v in ("vcc", "5v", "3v3", "3.3v", "vin", "vdd", "power")):
        return "#cc0000"
    if any(v in name for v in ("gnd", "ground", "0v", "agnd", "dgnd")):
        return "#1a1a1a"
    if any(v in name for v in ("sda", "scl", "i2c")):
        return "#007744"
    if any(v in name for v in ("spi", "mosi", "miso", "sck", "cs")):
        return "#770077"
    if any(v in name for v in ("tx", "rx", "uart", "serial")):
        return "#885500"
    if any(v in name for v in ("pwm", "motor", "servo")):
        return "#884400"
    if any(v in name for v in ("data", "dat", "sig", "out", "in")):
        return "#003388"
    palette = ["#005599", "#995500", "#007755", "#550077", "#557700", "#005577"]
    return palette[hash(net_name) % len(palette)]


# ── SchematicRenderer (moved from schematic_renderer.py) ────────────────────
class SchematicRenderer:

    # Symbol line/fill palette (EDA light theme)
    _SYM_STROKE  = "#1a1a2e"   # near-black for symbol lines
    _SYM_STROKE2 = "#333355"   # slightly lighter for secondary lines
    _PIN_COLOR   = "#1a1a2e"   # pin stub lines
    _TEXT_COLOR  = "#1a1a2e"   # general text
    _TEXT_REF    = "#111111"   # reference designator
    _TEXT_VAL    = "#555555"   # value/name
    _FILL_PASSIVE= "#ffffff"   # resistor, cap, diode body
    _FILL_MCU    = "#e8f0ff"   # MCU body fill
    _FILL_ACTIVE = "#f8f8ff"   # transistor/mosfet
    _FILL_POWER  = "#fffbe8"   # regulator/battery
    _FILL_SENSOR = "#e8fff4"   # sensor modules
    _FILL_DRIVER = "#fff0e8"   # motor drivers
    _FILL_COMM   = "#f4e8ff"   # RF/BT modules
    _FILL_DISP   = "#e8eeff"   # displays

    def render_schematic_svg(self, circuit_data: Dict[str, Any],
                              width: int = None, height: int = None) -> str:
        try:
            components = circuit_data.get("components", [])
            nets       = circuit_data.get("nets", [])
            sheet      = get_sheet_size(len(components))

            positions = _compute_positions(components, nets, sheet)

            # Honor manually saved positions (override computed placement)
            saved   = circuit_data.get("positions", {})
            grid_px = sheet["grid"] * _PX_PER_MM
            for comp_id, pos in saved.items():
                if isinstance(pos, dict) and "x" in pos and "y" in pos:
                    positions[comp_id] = snap_to_grid(
                        float(pos["x"]), float(pos["y"]), grid_px
                    )

            positions = _validate_positions(positions, sheet)

            # Canvas: fixed to the sheet size (no dynamic growth).
            w_px = int(sheet["w"] * _PX_PER_MM)
            h_px = int(sheet["h"] * _PX_PER_MM)

            dwg = svgwrite.Drawing(size=('100%', '100%'),
                                   viewBox=f"0 0 {w_px} {h_px}")
            self._draw_background(dwg, w_px, h_px)
            self._draw_schematic(dwg, circuit_data, components, nets, positions, sheet)
            tb_data = {**circuit_data, "sheet_name": sheet.get("name", "A4")}
            self._draw_title_block(dwg, tb_data, w_px, h_px)
            return dwg.tostring()
        except Exception as e:
            logger.error(f"Error renderizando esquemático: {e}")
            err = svgwrite.Drawing(size=(800, 100))
            err.add(err.rect(insert=(0, 0), size=(800, 100), fill="#fafafa"))
            err.add(err.text(f"Error: {e}", insert=(10, 50), fill="red",
                             font_size=16, font_family="monospace"))
            return err.tostring()

    def _draw_schematic(self, dwg, circuit_data: Dict, components: List[Dict],
                        nets: List[Dict], positions: Dict[str, Tuple],
                        sheet: Dict) -> None:
        """Draws all schematic elements. Receives pre-computed positions."""
        w_px = int(sheet["w"] * _PX_PER_MM)
        h_px = int(sheet["h"] * _PX_PER_MM)
        self._draw_galvanic_barrier(dwg, components, positions, w_px, h_px)
        self._draw_connections(dwg, nets, positions, w_px, h_px)
        self._draw_power_rails(dwg, nets, positions)
        for comp in components:
            pos = positions.get(comp["id"], (w_px // 2, h_px // 2))
            self._draw_component(dwg, comp, pos)
        self._draw_legend(dwg, nets, w_px, h_px)
        self._draw_annotations(dwg, circuit_data, w_px, h_px)

    # ── Background ──────────────────────────────────────────────────────────

    def _draw_background(self, dwg, width: int, height: int):
        """ISO 7200-style sheet: paper + outer frame + zone-ref band + inner frame."""
        border = BORDER_MM * _PX_PER_MM
        zr     = ZONE_REF_MM * _PX_PER_MM
        inner_x  = border + zr
        inner_y  = border + zr
        inner_w  = width  - 2 * (border + zr)
        inner_h  = height - 2 * (border + zr)
        ix2 = inner_x + inner_w
        iy2 = inner_y + inner_h

        # Paper
        dwg.add(dwg.rect(insert=(0, 0), size=(width, height), fill="#f5f6f7"))

        # Inner drawing-area background (slightly whiter)
        dwg.add(dwg.rect(insert=(inner_x, inner_y), size=(inner_w, inner_h),
                         fill="#fcfcfd"))

        # Fine grid inside drawing area only
        for gx in range(int(inner_x) + 20, int(ix2), 20):
            dwg.add(dwg.line(start=(gx, inner_y), end=(gx, iy2),
                             stroke="#eaecf2", stroke_width=0.4))
        for gy in range(int(inner_y) + 20, int(iy2), 20):
            dwg.add(dwg.line(start=(inner_x, gy), end=(ix2, gy),
                             stroke="#eaecf2", stroke_width=0.4))
        # Major grid (100px ≈ 25mm)
        for gx in range(int(inner_x) + 100, int(ix2), 100):
            dwg.add(dwg.line(start=(gx, inner_y), end=(gx, iy2),
                             stroke="#d4d7e0", stroke_width=0.7))
        for gy in range(int(inner_y) + 100, int(iy2), 100):
            dwg.add(dwg.line(start=(inner_x, gy), end=(ix2, gy),
                             stroke="#d4d7e0", stroke_width=0.7))

        # Outer frame
        dwg.add(dwg.rect(insert=(border, border),
                         size=(width - 2 * border, height - 2 * border),
                         fill="none", stroke="#222244", stroke_width=1.2))
        # Inner frame (drawing-area boundary)
        dwg.add(dwg.rect(insert=(inner_x, inner_y),
                         size=(inner_w, inner_h),
                         fill="none", stroke="#222244", stroke_width=2.0))

        # Zone references — columns 1..N (top + bottom)
        col_w = inner_w / ZONE_COLS
        for i in range(ZONE_COLS):
            cx = inner_x + (i + 0.5) * col_w
            dwg.add(dwg.text(str(i + 1),
                             insert=(cx, border + zr * 0.65),
                             font_size=11, fill="#222244",
                             font_family="Arial", text_anchor="middle",
                             font_weight="bold"))
            dwg.add(dwg.text(str(i + 1),
                             insert=(cx, iy2 + zr * 0.7),
                             font_size=11, fill="#222244",
                             font_family="Arial", text_anchor="middle",
                             font_weight="bold"))
            if i > 0:
                xt = inner_x + i * col_w
                dwg.add(dwg.line(start=(xt, border), end=(xt, inner_y),
                                 stroke="#222244", stroke_width=0.6))
                dwg.add(dwg.line(start=(xt, iy2),
                                 end=(xt, height - border),
                                 stroke="#222244", stroke_width=0.6))

        # Zone references — rows A..N (left + right)
        row_h = inner_h / ZONE_ROWS
        for j in range(ZONE_ROWS):
            cy = inner_y + (j + 0.5) * row_h
            letter = chr(ord("A") + j)
            dwg.add(dwg.text(letter,
                             insert=(border + zr * 0.5, cy + 4),
                             font_size=11, fill="#222244",
                             font_family="Arial", text_anchor="middle",
                             font_weight="bold"))
            dwg.add(dwg.text(letter,
                             insert=(ix2 + zr * 0.5, cy + 4),
                             font_size=11, fill="#222244",
                             font_family="Arial", text_anchor="middle",
                             font_weight="bold"))
            if j > 0:
                yt = inner_y + j * row_h
                dwg.add(dwg.line(start=(border, yt), end=(inner_x, yt),
                                 stroke="#222244", stroke_width=0.6))
                dwg.add(dwg.line(start=(ix2, yt),
                                 end=(width - border, yt),
                                 stroke="#222244", stroke_width=0.6))

        # Corner brackets (engineering-drawing style)
        bk = 14
        for cx, cy, sx, sy in [
            (border, border, 1, 1),
            (width - border, border, -1, 1),
            (border, height - border, 1, -1),
            (width - border, height - border, -1, -1),
        ]:
            dwg.add(dwg.line(start=(cx, cy), end=(cx + sx * bk, cy),
                             stroke="#222244", stroke_width=2))
            dwg.add(dwg.line(start=(cx, cy), end=(cx, cy + sy * bk),
                             stroke="#222244", stroke_width=2))

    # ── Title block (EDA-style bottom frame) ────────────────────────────────

    def _draw_title_block(self, dwg, circuit_data: Dict, width: int, height: int):
        """ISO 7200-style title block — anchored to bottom-right corner of inner frame."""
        border = BORDER_MM * _PX_PER_MM
        zr     = ZONE_REF_MM * _PX_PER_MM
        tb_w   = TITLE_BLOCK_W_MM * _PX_PER_MM
        tb_h   = TITLE_BLOCK_H_MM * _PX_PER_MM
        # Sit flush with the inner frame, in the bottom-right corner
        x0 = width - border - zr - tb_w
        y0 = height - border - zr - tb_h
        x1, y1 = x0 + tb_w, y0 + tb_h

        name   = circuit_data.get("name", "Sin nombre")[:50]
        desc   = circuit_data.get("description", "")[:90]
        power  = circuit_data.get("power", "—") or "—"
        mcu    = circuit_data.get("selected_mcu", "—") or "—"
        domain = circuit_data.get("detected_domain", "generic") or "generic"
        n_comp = len(circuit_data.get("components", []))
        sheet_name = circuit_data.get("sheet_name", "A4")
        drc = circuit_data.get("drc", {})
        passed = drc.get("passed", True)

        # Background
        dwg.add(dwg.rect(insert=(x0, y0), size=(tb_w, tb_h),
                         fill="#fafbff", stroke="#222244", stroke_width=1.5))

        # Row heights
        r1 = tb_h * 0.42
        r2 = tb_h * 0.34
        r3 = tb_h - r1 - r2
        dwg.add(dwg.line(start=(x0, y0 + r1), end=(x1, y0 + r1),
                         stroke="#444466", stroke_width=0.8))
        dwg.add(dwg.line(start=(x0, y0 + r1 + r2), end=(x1, y0 + r1 + r2),
                         stroke="#444466", stroke_width=0.8))
        # Row1: title (75%) + DRC badge (25%)
        col_drc = x0 + tb_w * 0.74
        dwg.add(dwg.line(start=(col_drc, y0), end=(col_drc, y0 + r1),
                         stroke="#444466", stroke_width=0.8))
        # Row2 cells: MCU | POWER | DOMAIN | COMP
        col2 = [x0 + tb_w * f for f in (0.25, 0.50, 0.75)]
        for cx in col2:
            dwg.add(dwg.line(start=(cx, y0 + r1), end=(cx, y0 + r1 + r2),
                             stroke="#444466", stroke_width=0.6))

        # TITLE
        dwg.add(dwg.text("TITLE", insert=(x0 + 8, y0 + 11),
                         font_size=7, fill="#666688", font_family="Arial"))
        dwg.add(dwg.text(name, insert=(x0 + 8, y0 + r1 - 8),
                         font_size=14, fill="#111133", font_family="Arial",
                         font_weight="bold"))

        # DRC badge
        badge_color = "#1a7a1a" if passed else "#aa1111"
        badge_label = "DRC ✓" if passed else "DRC ✗"
        dwg.add(dwg.rect(insert=(col_drc + 6, y0 + r1 * 0.18),
                         size=(x1 - col_drc - 12, r1 * 0.62),
                         fill=badge_color, fill_opacity=0.15,
                         stroke=badge_color, stroke_width=1, rx=3))
        dwg.add(dwg.text(badge_label,
                         insert=((col_drc + x1) / 2, y0 + r1 * 0.62),
                         font_size=12, fill=badge_color, font_family="Arial",
                         font_weight="bold", text_anchor="middle"))

        # Row 2 cells
        cells = [
            ("MCU",    str(mcu)[:14],    "#223399"),
            ("POWER",  str(power)[:14],  "#cc3300"),
            ("DOMAIN", str(domain)[:14], "#117755"),
            ("COMP",   str(n_comp),      "#333355"),
        ]
        cell_xs = [x0] + col2 + [x1]
        for i, (lbl, val, color) in enumerate(cells):
            cxL = cell_xs[i]
            dwg.add(dwg.text(lbl, insert=(cxL + 6, y0 + r1 + 11),
                             font_size=7, fill="#666688", font_family="Arial"))
            dwg.add(dwg.text(val, insert=(cxL + 6, y0 + r1 + r2 - 8),
                             font_size=10, fill=color, font_family="monospace"))

        # Row 3: description (left) + sheet info (right)
        dwg.add(dwg.text(desc, insert=(x0 + 8, y0 + r1 + r2 + r3 * 0.65),
                         font_size=8, fill="#555577", font_family="Arial"))
        dwg.add(dwg.text(f"SHEET {sheet_name}  ·  Stratum EDA",
                         insert=(x1 - 8, y0 + r1 + r2 + r3 * 0.65),
                         font_size=8, fill="#9999bb", font_family="Arial",
                         font_style="italic", text_anchor="end"))

    # ── F2.4 — Galvanic isolation barrier ───────────────────────────────────

    def _draw_galvanic_barrier(self, dwg, components: List[Dict],
                                positions: Dict[str, Tuple[int, int]],
                                width: int, height: int):
        """
        Draws a vertical dashed line with zigzag separating the AC/HV zone
        from the LV control zone. Only drawn if at least one AC-zone component
        is present.
        """
        ac_xs = [
            positions[c["id"]][0]
            for c in components
            if c["id"] in positions and _classify_zone(c) == "ac"
        ]
        mcu_xs = [
            positions[c["id"]][0]
            for c in components
            if c["id"] in positions and _classify_zone(c) == "mcu"
        ]
        if not ac_xs or not mcu_xs:
            return  # not a HV circuit — skip the barrier

        bx = (max(ac_xs) + min(mcu_xs)) // 2
        y_top, y_bot = 60, height - 110

        # Two parallel dashed lines forming the barrier band
        for offset in (-6, 6):
            dwg.add(dwg.line(
                start=(bx + offset, y_top), end=(bx + offset, y_bot),
                stroke="#aa3300", stroke_width=1.2,
                stroke_dasharray="6,4", stroke_opacity=0.85,
            ))

        # Zigzag pattern in the middle (galvanic isolation pictogram)
        zigzag_step = 18
        zy = y_top + 30
        while zy < y_bot - 30:
            dwg.add(dwg.path(
                d=f"M {bx-5} {zy} L {bx+5} {zy+zigzag_step//2} "
                  f"L {bx-5} {zy+zigzag_step} L {bx+5} {zy+int(zigzag_step*1.5)}",
                fill="none", stroke="#aa3300", stroke_width=1.4,
                stroke_opacity=0.7,
            ))
            zy += zigzag_step * 2

        # Top label
        dwg.add(dwg.rect(
            insert=(bx - 80, y_top - 4), size=(160, 22),
            fill="#fff0e8", stroke="#aa3300", stroke_width=1, rx=4,
        ))
        dwg.add(dwg.text(
            "BARRERA GALVÁNICA", insert=(bx, y_top + 11),
            font_size=10, fill="#aa3300", font_family="monospace",
            text_anchor="middle", font_weight="bold",
        ))

        # Side warnings (HV ↔ LV)
        dwg.add(dwg.text(
            "⚠ HV", insert=(bx - 14, y_top + 35),
            font_size=11, fill="#aa3300", font_family="Arial",
            font_weight="bold", text_anchor="end",
        ))
        dwg.add(dwg.text(
            "LV", insert=(bx + 14, y_top + 35),
            font_size=11, fill="#117755", font_family="Arial",
            font_weight="bold", text_anchor="start",
        ))

    # ── Net connections (F2.1 — net labels for distant nodes) ──────────────

    _LABEL_DISTANCE_THRESHOLD = 220  # fallback — overridden by dynamic threshold in _draw_connections

    def _draw_net_label(self, dwg, name: str, pos: Tuple[int, int],
                        color: str, direction: str = "right"):
        """
        Draw a KiCad-style net label flag at (pos) with text.
        direction: 'right' (default) | 'left' | 'up' | 'down'
        """
        x, y = pos
        label_w = max(40, len(name) * 6 + 14)
        if direction == "right":
            # Flag points right: tail at (x,y), head at (x+18,y), text further right
            poly = [(x, y), (x + 8, y - 7), (x + 8 + label_w, y - 7),
                    (x + 8 + label_w, y + 7), (x + 8, y + 7)]
            tx, anchor = x + 12, "start"
        elif direction == "left":
            poly = [(x, y), (x - 8, y - 7), (x - 8 - label_w, y - 7),
                    (x - 8 - label_w, y + 7), (x - 8, y + 7)]
            tx, anchor = x - 12, "end"
        elif direction == "up":
            poly = [(x, y), (x - 7, y - 8), (x - 7, y - 8 - label_w),
                    (x + 7, y - 8 - label_w), (x + 7, y - 8)]
            tx, anchor = x, "middle"
            ty = y - 16
        else:  # down
            poly = [(x, y), (x - 7, y + 8), (x - 7, y + 8 + label_w),
                    (x + 7, y + 8 + label_w), (x + 7, y + 8)]
            tx, anchor = x, "middle"
            ty = y + 22
        dwg.add(dwg.polygon(poly, fill="#fffdf0", stroke=color, stroke_width=1))
        if direction in ("right", "left"):
            dwg.add(dwg.text(name, insert=(tx, y + 3),
                             font_size=9, fill=color,
                             font_family="monospace", text_anchor=anchor,
                             font_weight="bold"))
        else:
            dwg.add(dwg.text(name, insert=(tx, ty),
                             font_size=9, fill=color,
                             font_family="monospace", text_anchor="middle",
                             font_weight="bold"))

    @staticmethod
    def _rects_overlap(a, b) -> bool:
        return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])

    def _alloc_label_dx(self, label_rects: list, cx: float, cy: float,
                         label_w: int, direction: str) -> tuple:
        """Returns (stub_dx, rect) — stub length grown until label rect doesn't collide."""
        sign = 1 if direction == "right" else -1
        dx = 18
        rect = (0, 0, 0, 0)
        for _ in range(6):
            text_x0 = cx + sign * (dx + 8)
            text_x1 = text_x0 + sign * label_w
            x_left  = min(text_x0, text_x1)
            x_right = max(text_x0, text_x1)
            rect = (x_left, cy - 9, x_right, cy + 9)
            if not any(self._rects_overlap(rect, r) for r in label_rects):
                return sign * dx, rect
            dx += 28
        return sign * dx, rect

    def _draw_connections(self, dwg, nets, positions, canvas_w=None, canvas_h=None):
        """Draw nets — long-distance ones use net-label flags (collision-aware);
        short ones use a vertical trunk + horizontal stubs (Manhattan tree)."""
        label_rects: list = []
        for net in nets:
            try:
                name  = net.get("name", "")
                color = _net_color(name)
                nodes = net.get("nodes", [])
                coords = [
                    positions[n.split(".")[0]]
                    for n in nodes
                    if n.split(".")[0] in positions
                ]
                if len(coords) < 2:
                    continue
                xs = [c[0] for c in coords]
                ys = [c[1] for c in coords]
                span_x = max(xs) - min(xs)
                span_y = max(ys) - min(ys)
                threshold = (canvas_w * 0.55) if canvas_w else self._LABEL_DISTANCE_THRESHOLD
                use_labels = (
                    span_x > threshold
                    or span_y > ((canvas_h * 0.4) if canvas_h else threshold)
                )
                if use_labels:
                    avg_x = sum(xs) / len(xs)
                    label_w = max(40, len(name) * 6 + 14)
                    for cx, cy in coords:
                        direction = "right" if cx <= avg_x else "left"
                        stub_dx, rect = self._alloc_label_dx(
                            label_rects, cx, cy, label_w, direction)
                        dwg.add(dwg.line(
                            start=(cx, cy), end=(cx + stub_dx, cy),
                            stroke=color, stroke_width=1.8))
                        self._draw_net_label(dwg, name, (cx + stub_dx, cy),
                                             color, direction=direction)
                        dwg.add(dwg.circle(center=(cx, cy), r=3, fill=color))
                        label_rects.append(rect)
                else:
                    # Manhattan tree: vertical trunk at barycenter X, horizontal stubs.
                    trunk_x = sum(xs) / len(xs)
                    y_min, y_max = min(ys), max(ys)
                    if y_max - y_min > 2:
                        dwg.add(dwg.line(
                            start=(trunk_x, y_min), end=(trunk_x, y_max),
                            stroke=color, stroke_width=1.8))
                    for cx, cy in coords:
                        if abs(cx - trunk_x) > 1:
                            dwg.add(dwg.line(
                                start=(cx, cy), end=(trunk_x, cy),
                                stroke=color, stroke_width=1.8))
                        dwg.add(dwg.circle(center=(cx, cy), r=3.5, fill=color))
                    # Junction dots where stubs meet the trunk
                    for cy in ys:
                        if cy != y_min and cy != y_max:
                            dwg.add(dwg.circle(center=(trunk_x, cy), r=2.4, fill=color))
                    # Net name label — placed on the trunk, offset right, with
                    # collision check against previously placed labels.
                    # Try positions: trunk top, centroid, bottom (in that order)
                    # then bump alternately ±16 px until clear.
                    label_w = len(name) * 5 + 12
                    lx = int(trunk_x + 6)
                    candidates = [y_min - 4, (y_min + y_max) // 2, y_max + 14]
                    rect = (lx - 2, 0, lx + label_w, 0)
                    chosen_ly = candidates[0]
                    for cand in candidates:
                        rect = (lx - 2, cand - 11, lx + label_w, cand + 4)
                        if not any(self._rects_overlap(rect, r) for r in label_rects):
                            chosen_ly = cand
                            break
                    else:
                        # All candidates collide — bump up incrementally
                        chosen_ly = candidates[0]
                        for k in range(1, 6):
                            ly = chosen_ly - k * 16
                            rect = (lx - 2, ly - 11, lx + label_w, ly + 4)
                            if not any(self._rects_overlap(rect, r) for r in label_rects):
                                chosen_ly = ly
                                break
                    ly = chosen_ly
                    rect = (lx - 2, ly - 11, lx + label_w, ly + 4)
                    dwg.add(dwg.rect(
                        insert=(lx - 2, ly - 11), size=(label_w, 14),
                        fill="#ffffee", stroke=color, stroke_width=0.7, rx=2))
                    dwg.add(dwg.text(
                        name, insert=(lx + 2, ly),
                        font_size=9, fill=color, font_family="monospace"))
                    label_rects.append(rect)
            except Exception as ex:
                logger.warning(
                    f"_draw_connections skipped net '{net.get('name','')}': {ex}")

    def _draw_power_rails(self, dwg, nets: List[Dict],
                          positions: Dict[str, Tuple[int, int]]):
        for net in nets:
            name = net.get("name","")
            nl   = name.lower()
            nodes = net.get("nodes",[])
            if not nodes:
                continue
            # Get first valid component position
            pos = None
            for n in nodes:
                cid = n.split(".")[0]
                if cid in positions:
                    pos = positions[cid]
                    break
            if not pos:
                continue
            px, py = pos
            if any(v in nl for v in ("vcc","5v","3v3","vin","vdd","power")):
                # VCC: upward arrow above connection point
                ax, ay = px, py - 45
                dwg.add(dwg.line(start=(px, py-20), end=(ax, ay+18),
                                 stroke="#cc0000", stroke_width=1.5))
                # Arrow head
                dwg.add(dwg.polygon([(ax,ay), (ax-6,ay+10), (ax+6,ay+10)],
                                    fill="#cc0000"))
                # Label
                dwg.add(dwg.rect(insert=(ax-16, ay-14), size=(32,14),
                                 fill="#fff0f0", stroke="#cc0000",
                                 stroke_width=0.8, rx=2))
                dwg.add(dwg.text(name.upper(), insert=(ax, ay-3),
                                 font_size=9, fill="#cc0000", font_family="monospace",
                                 font_weight="bold", text_anchor="middle"))
            elif any(v in nl for v in ("gnd","ground","0v")):
                # GND: 3-line symbol below connection point
                gx, gy = px, py + 20
                dwg.add(dwg.line(start=(px, py+18), end=(gx, gy),
                                 stroke="#1a1a1a", stroke_width=1.5))
                for i, w in enumerate([20, 13, 6]):
                    yy = gy + i*5
                    dwg.add(dwg.line(start=(gx-w, yy), end=(gx+w, yy),
                                     stroke="#1a1a1a", stroke_width=2-i*0.3))
                dwg.add(dwg.text("GND", insert=(gx, gy+22),
                                 font_size=8, fill="#1a1a1a", font_family="monospace",
                                 text_anchor="middle"))

    # ── Component dispatcher ─────────────────────────────────────────────────

    def _draw_component(self, dwg, comp: Dict, pos: Tuple[int, int]):
        x, y = pos
        t = comp.get("resolved_type", comp.get("type", "generic")).lower()

        # ── Try KiCad symbol first ──────────────────────────────────────────
        if _kicad.render(dwg, x, y, t):
            ref  = comp.get("id", "?")
            val  = comp.get("value", "")
            unit = comp.get("unit", "")
            name = comp.get("name", "")
            dwg.add(dwg.text(ref, insert=(x, y - 42),
                             font_size=10, fill=self._TEXT_REF,
                             font_family="monospace", text_anchor="middle",
                             font_weight="bold"))
            if val:
                dwg.add(dwg.text(f"{val}{unit}", insert=(x, y - 30),
                                 font_size=9, fill=self._TEXT_VAL,
                                 font_family="monospace", text_anchor="middle"))
            if name and name != ref:
                dwg.add(dwg.text(name[:24], insert=(x, y + 56),
                                 font_size=8, fill="#445588",
                                 font_family="Arial", text_anchor="middle"))
            return

        dispatch = {
            "resistor":              self._sym_resistor,
            "led":                   self._sym_led,
            "led_rgb":               self._sym_led,
            "capacitor":             self._sym_capacitor,
            "capacitor_electrolytic":self._sym_capacitor,
            "button":                self._sym_button,
            "arduino_uno":           self._sym_mcu,
            "arduino_nano":          self._sym_mcu,
            "arduino_mega":          self._sym_mcu,
            "arduino_micro":         self._sym_mcu,
            "esp32":                 self._sym_mcu,
            "esp8266":               self._sym_mcu,
            "stm32":                 self._sym_mcu,
            "pico":                  self._sym_mcu,
            "raspberry_pi_pico":     self._sym_mcu,
            "relay":                 self._sym_relay,
            "relay_module":          self._sym_relay,
            "mosfet":                self._sym_mosfet,
            "mosfet_n":              self._sym_mosfet,
            "transistor":            self._sym_transistor,
            "diode":                 self._sym_diode,
            "motor":                 self._sym_motor,
            "dc_motor":              self._sym_motor,
            "stepper":               self._sym_stepper,
            "stepper_motor":         self._sym_stepper,
            "servo":                 self._sym_servo,
            "motor_driver":          self._sym_l298n,
            "l298n":                 self._sym_l298n,
            "drv8825":               self._sym_stepper_driver,
            "a4988":                 self._sym_stepper_driver,
            "tb6600":                self._sym_stepper_driver,
            "uln2003":               self._sym_ic_generic,
            "buzzer":                self._sym_buzzer,
            "sensor":                self._sym_sensor,
            "moisture_sensor":       self._sym_moisture,
            "hc_sr04":               self._sym_ultrasonic,
            "ultrasonic":            self._sym_ultrasonic,
            "ultrasonic_sensor":     self._sym_ultrasonic,
            "display":               self._sym_display,
            "oled":                  self._sym_oled,
            "lcd":                   self._sym_display,
            "bmp280":                self._sym_bmp280,
            "transistor_npn":        self._sym_transistor,
            "voltage_regulator":     self._sym_regulator,
            "lm7805":                self._sym_regulator,
            "ams1117":               self._sym_regulator,
            "lm317":                 self._sym_regulator,
            "regulator":             self._sym_regulator,
            "buck_converter":        self._sym_converter,
            "boost_converter":       self._sym_converter,
            "buck_boost":            self._sym_converter,
            "wifi_module":           self._sym_rf_module,
            "bluetooth":             self._sym_rf_module,
            "hc05":                  self._sym_rf_module,
            "hc_05":                 self._sym_rf_module,
            "nrf24l01":              self._sym_rf_module,
            "rf_module":             self._sym_rf_module,
            "lora":                  self._sym_rf_module,
            "connector":             self._sym_connector,
            "header":                self._sym_connector,
            "pin_header":            self._sym_connector,
            "terminal_block":        self._sym_connector,
            "inductor":              self._sym_inductor,
            "battery":               self._sym_battery,
            "battery_18650":         self._sym_battery,
            "lipo":                  self._sym_battery,
            # RTC modules
            "rtc":                   self._sym_rtc,
            "ds3231":                self._sym_rtc,
            "ds1307":                self._sym_rtc,
            "pcf8523":               self._sym_rtc,
            # Explicit diode part numbers
            "1n4007":                self._sym_diode,
            "1n5819":                self._sym_diode,
            "1n4148":                self._sym_diode,
            "zener":                 self._sym_diode,
            # Explicit transistors
            "bc547":                 self._sym_transistor,
            "bc557":                 self._sym_transistor,
            "2n2222":                self._sym_transistor,
            # Explicit MOSFETs
            "irf520":                self._sym_mosfet,
            "irf540":                self._sym_mosfet,
            "irfz44":                self._sym_mosfet,
            # Power / protection
            "transformer":           self._sym_transformer,
            "bridge_rectifier":      self._sym_bridge_rectifier,
            "fuse":                  self._sym_fuse,
            "fuse_holder":           self._sym_fuse,
            "varistor":              self._sym_varistor,
            "mov":                   self._sym_varistor,
            "x_capacitor":           self._sym_capacitor,
            "mosfet_driver":         self._sym_mosfet_driver,
            "gate_driver":           self._sym_mosfet_driver,
            "uln2003":               self._sym_mosfet_driver,
            "ir2104":                self._sym_mosfet_driver,
            "connector_ac":          self._sym_connector_ac,
            "iec_connector":         self._sym_connector_ac,
        }
        draw_fn = dispatch.get(t)
        if draw_fn is not None:
            draw_fn(dwg, x, y, comp)
        elif not _kicad.render(dwg, x, y, t):
            self._sym_generic(dwg, x, y, comp)

        # Reference above component
        ref = comp.get("id","?")
        val = comp.get("value","")
        unit = comp.get("unit","")
        dwg.add(dwg.text(ref, insert=(x, y-38),
                         font_size=10, fill=self._TEXT_REF,
                         font_family="monospace", text_anchor="middle",
                         font_weight="bold"))
        # Value below reference
        if val:
            dwg.add(dwg.text(f"{val}{unit}", insert=(x, y-26),
                             font_size=9, fill=self._TEXT_VAL,
                             font_family="monospace", text_anchor="middle"))
        # Name below component
        name = comp.get("name","")
        if name and name != ref:
            dwg.add(dwg.text(name[:24], insert=(x, y+50),
                             font_size=8, fill="#445588",
                             font_family="Arial", text_anchor="middle"))

    # ── Symbol primitives (EDA light theme: dark lines, light fills) ─────────

    def _sym_resistor(self, dwg, x, y, comp):
        """IEC rectangle resistor."""
        W, H = 34, 14
        # Body
        dwg.add(dwg.rect(insert=(x-W//2, y-H//2), size=(W,H),
                         fill=self._FILL_PASSIVE, stroke=self._SYM_STROKE, stroke_width=1.5))
        # Lead stubs
        for x0, x1 in [(x-W//2-14, x-W//2), (x+W//2, x+W//2+14)]:
            dwg.add(dwg.line(start=(x0,y), end=(x1,y),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
        # Value inside
        val = f"{comp.get('value','')}{comp.get('unit','Ω')}"
        dwg.add(dwg.text(val, insert=(x, y+4),
                         font_size=8, fill="#aa6600",
                         font_family="monospace", text_anchor="middle"))

    def _sym_led(self, dwg, x, y, comp):
        """LED — triangle + cathode bar + light arrows."""
        color = comp.get("color","yellow")
        svg_colors = {"red":"#ee2222","green":"#22bb22","blue":"#2244ee",
                      "yellow":"#ddcc00","white":"#aaaaaa","orange":"#ee7700","rgb":"#884499"}
        fill_c = svg_colors.get(color,"#ddcc00")
        tri_pts = [(x-14, y-12),(x-14, y+12),(x+10, y)]
        dwg.add(dwg.polygon(tri_pts, fill=fill_c, fill_opacity=0.35,
                            stroke=fill_c, stroke_width=1.8))
        dwg.add(dwg.line(start=(x+10,y-13), end=(x+10,y+13),
                         stroke=fill_c, stroke_width=2.5))
        for x0, x1 in [(x-25,x-14),(x+10,x+26)]:
            dwg.add(dwg.line(start=(x0,y), end=(x1,y),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
        # Light arrows
        for dx, dy in [(18,-10),(23,-15)]:
            dwg.add(dwg.line(start=(x+dx-4,y-dy), end=(x+dx+5,y-dy-9),
                             stroke=fill_c, stroke_width=1.2))
            # Arrow head
            ang = math.atan2(-9,9)
            dwg.add(dwg.polygon([
                (x+dx+5, y-dy-9),
                (x+dx+5-4*math.cos(ang+0.5), y-dy-9-4*math.sin(ang+0.5)),
                (x+dx+5-4*math.cos(ang-0.5), y-dy-9-4*math.sin(ang-0.5)),
            ], fill=fill_c))

    def _sym_capacitor(self, dwg, x, y, comp):
        """Capacitor — two parallel plates."""
        gap, pw = 5, 22
        dwg.add(dwg.line(start=(x-pw,y-gap), end=(x+pw,y-gap),
                         stroke=self._SYM_STROKE, stroke_width=2.5))
        dwg.add(dwg.line(start=(x-pw,y+gap), end=(x+pw,y+gap),
                         stroke=self._SYM_STROKE, stroke_width=2.5))
        for y0, y1 in [(y-20,y-gap),(y+gap,y+20)]:
            dwg.add(dwg.line(start=(x,y0), end=(x,y1),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
        dwg.add(dwg.text("+", insert=(x+25,y-2),
                         font_size=12, fill="#1a8822", font_family="Arial",
                         font_weight="bold"))

    def _sym_button(self, dwg, x, y, comp):
        """SPST push button."""
        for cx, x2 in [(x-22,x-8),(x+8,x+22)]:
            dwg.add(dwg.line(start=(cx,y), end=(x2,y),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
        dwg.add(dwg.circle(center=(x-8,y), r=2.5,
                           fill=self._SYM_STROKE, stroke="none"))
        dwg.add(dwg.circle(center=(x+8,y), r=2.5,
                           fill=self._SYM_STROKE, stroke="none"))
        dwg.add(dwg.line(start=(x-8,y), end=(x+5,y-11),
                         stroke=self._SYM_STROKE, stroke_width=1.8))
        # Push indicator
        dwg.add(dwg.line(start=(x+2,y-18), end=(x+2,y-10),
                         stroke="#666688", stroke_width=1, stroke_dasharray="2,2"))

    def _sym_mcu(self, dwg, x, y, comp):
        """MCU / module — IC box with pin stubs."""
        W, H = 90, 60
        name = comp.get("name", comp.get("id","MCU"))
        # Body
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2), size=(W,H),
                         fill=self._FILL_MCU, stroke=self._SYM_STROKE, stroke_width=2, rx=2))
        # Header bar
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2), size=(W,18),
                         fill="#4466aa", fill_opacity=0.18, rx=2))
        short = name.replace("Arduino ","").replace(" Uno","").replace(" Nano","")[:12]
        dwg.add(dwg.text(short, insert=(x,y-H//2+13),
                         font_size=11, fill="#223388",
                         font_family="monospace", text_anchor="middle", font_weight="bold"))
        dwg.add(dwg.text(comp.get("id","U1"), insert=(x,y+6),
                         font_size=9, fill="#555577",
                         font_family="monospace", text_anchor="middle"))
        # Pin stubs — left and right sides (simplified)
        n_pins = 4
        for side_sign, label_x in [(-1, x-W//2-14), (1, x+W//2+14)]:
            for i in range(n_pins):
                py_ = y - 16 + i*11
                x_body = x + side_sign * W//2
                x_tip  = x + side_sign * (W//2 + 10)
                dwg.add(dwg.line(start=(x_body,py_), end=(x_tip,py_),
                                 stroke=self._PIN_COLOR, stroke_width=1))
                # Pin number
                dwg.add(dwg.text(str(i+1 if side_sign<0 else n_pins*2-i),
                                 insert=(label_x, py_+3),
                                 font_size=6, fill="#888899",
                                 font_family="monospace", text_anchor="middle"))

    def _sym_relay(self, dwg, x, y, comp):
        """Relay — coil + contact symbol."""
        # Coil rectangle
        dwg.add(dwg.rect(insert=(x-20,y-12), size=(40,24),
                         fill=self._FILL_PASSIVE, stroke="#886600", stroke_width=1.8))
        # Coil winding lines
        for i in range(5):
            xi = x-14 + i*7
            dwg.add(dwg.line(start=(xi,y-8), end=(xi,y+8),
                             stroke="#886600", stroke_width=0.8, stroke_opacity=0.5))
        dwg.add(dwg.text("K", insert=(x,y+5),
                         font_size=10, fill="#886600",
                         font_family="monospace", text_anchor="middle"))
        # Contact symbol above coil
        dwg.add(dwg.line(start=(x-8,y-22), end=(x-8,y-32), stroke=self._SYM_STROKE, stroke_width=1.5))
        dwg.add(dwg.line(start=(x+8,y-22), end=(x+8,y-32), stroke=self._SYM_STROKE, stroke_width=1.5))
        dwg.add(dwg.line(start=(x-8,y-28), end=(x+4,y-36), stroke=self._SYM_STROKE, stroke_width=1.5))
        # Coil leads
        for x0,x1 in [(x-34,x-20),(x+20,x+34)]:
            dwg.add(dwg.line(start=(x0,y), end=(x1,y),
                             stroke=self._PIN_COLOR, stroke_width=1.5))

    def _sym_mosfet(self, dwg, x, y, comp):
        """N-Channel MOSFET."""
        # Channel body line
        dwg.add(dwg.line(start=(x,y-22), end=(x,y+22),
                         stroke=self._SYM_STROKE, stroke_width=2.2))
        # Gate
        dwg.add(dwg.line(start=(x-22,y), end=(x-5,y),
                         stroke=self._PIN_COLOR, stroke_width=1.5))
        dwg.add(dwg.line(start=(x-5,y-18), end=(x-5,y+18),
                         stroke=self._SYM_STROKE, stroke_width=2.2))
        gap = 4
        dwg.add(dwg.line(start=(x-5+gap,y-18), end=(x-5+gap,y+18),
                         stroke=self._SYM_STROKE, stroke_width=1.5,
                         stroke_dasharray="3,2"))
        # Drain / Source
        for sign, lbl in [(-1,"D"),(1,"S")]:
            dwg.add(dwg.line(start=(x-1,y+sign*12), end=(x+20,y+sign*12),
                             stroke=self._SYM_STROKE, stroke_width=1.5))
            dwg.add(dwg.line(start=(x+20,y+sign*12), end=(x+20,y+sign*24),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
            dwg.add(dwg.text(lbl, insert=(x+24,y+sign*14+4),
                             font_size=8, fill=self._TEXT_COLOR, font_family="Arial"))
        # Arrow (source)
        arr = [(x+14,y+12),(x+20,y+8),(x+20,y+16)]
        dwg.add(dwg.polygon(arr, fill=self._SYM_STROKE))
        dwg.add(dwg.text("G", insert=(x-28,y+4),
                         font_size=8, fill=self._TEXT_COLOR, font_family="Arial"))

    def _sym_transistor(self, dwg, x, y, comp):
        """NPN transistor."""
        # Base
        dwg.add(dwg.line(start=(x-22,y), end=(x,y),
                         stroke=self._PIN_COLOR, stroke_width=1.5))
        dwg.add(dwg.line(start=(x,y-20), end=(x,y+20),
                         stroke=self._SYM_STROKE, stroke_width=2.5))
        # Collector / Emitter
        dwg.add(dwg.line(start=(x,y-10), end=(x+20,y-22),
                         stroke=self._SYM_STROKE, stroke_width=1.5))
        dwg.add(dwg.line(start=(x,y+10), end=(x+20,y+22),
                         stroke=self._SYM_STROKE, stroke_width=1.5))
        # Emitter arrow
        arr = [(x+14,y+17),(x+22,y+23),(x+12,y+24)]
        dwg.add(dwg.polygon(arr, fill=self._SYM_STROKE))
        for lbl, lx, ly_ in [("B",x-28,y+4),("C",x+22,y-20),("E",x+22,y+24)]:
            dwg.add(dwg.text(lbl, insert=(lx,ly_),
                             font_size=8, fill=self._TEXT_COLOR, font_family="Arial"))

    def _sym_diode(self, dwg, x, y, comp):
        """Diode (signal/flyback)."""
        tri = [(x-14,y-10),(x-14,y+10),(x+10,y)]
        dwg.add(dwg.polygon(tri, fill="#dddddd",
                            stroke=self._SYM_STROKE, stroke_width=1.8))
        dwg.add(dwg.line(start=(x+10,y-12), end=(x+10,y+12),
                         stroke=self._SYM_STROKE, stroke_width=2.2))
        for x0,x1 in [(x-26,x-14),(x+10,x+26)]:
            dwg.add(dwg.line(start=(x0,y), end=(x1,y),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
        for lbl,lx in [("A",x-28),("K",x+18)]:
            dwg.add(dwg.text(lbl, insert=(lx,y+4),
                             font_size=7, fill=self._TEXT_COLOR, font_family="Arial"))

    def _sym_motor(self, dwg, x, y, comp):
        """DC Motor — circle with M."""
        dwg.add(dwg.circle(center=(x,y), r=22,
                           fill=self._FILL_PASSIVE, stroke="#884400", stroke_width=2))
        dwg.add(dwg.text("M", insert=(x,y+7),
                         font_size=20, fill="#884400",
                         font_family="Arial", font_weight="bold", text_anchor="middle"))
        for x0,x1 in [(x-36,x-22),(x+22,x+36)]:
            dwg.add(dwg.line(start=(x0,y), end=(x1,y),
                             stroke=self._PIN_COLOR, stroke_width=1.5))

    def _sym_buzzer(self, dwg, x, y, comp):
        """Buzzer / piezo."""
        dwg.add(dwg.ellipse(center=(x,y), r=(17,12),
                            fill="#f0f0ff", stroke="#444488", stroke_width=1.8))
        for r_off in (21,27):
            dwg.add(dwg.path(
                d=f"M {x+r_off} {y-9} Q {x+r_off+7} {y} {x+r_off} {y+9}",
                fill="none", stroke="#444488", stroke_width=1.2))
        dwg.add(dwg.text("~", insert=(x,y+6),
                         font_size=14, fill="#444488",
                         font_family="Arial", text_anchor="middle"))
        for offs in [(-6,6)]:
            dwg.add(dwg.line(start=(x-24,y+offs[0]), end=(x-17,y+offs[0]),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
            dwg.add(dwg.line(start=(x-24,y+offs[1]), end=(x-17,y+offs[1]),
                             stroke=self._PIN_COLOR, stroke_width=1.5))

    def _sym_sensor(self, dwg, x, y, comp):
        """Generic sensor box."""
        W, H = 38, 30
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2), size=(W,H),
                         fill=self._FILL_SENSOR, stroke="#117755", stroke_width=1.8, rx=4))
        dwg.add(dwg.text("S", insert=(x,y+6),
                         font_size=16, fill="#117755",
                         font_family="Arial", font_weight="bold", text_anchor="middle"))
        for off in (-8,0,8):
            dwg.add(dwg.line(start=(x+W//2,y+off), end=(x+W//2+12,y+off),
                             stroke="#117755", stroke_width=1, stroke_dasharray="2,2"))

    def _sym_display(self, dwg, x, y, comp):
        """OLED/LCD display."""
        W, H = 64, 38
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2), size=(W,H),
                         fill=self._FILL_DISP, stroke="#334499", stroke_width=2, rx=3))
        # Screen area
        dwg.add(dwg.rect(insert=(x-W//2+4,y-H//2+4), size=(W-8,H-8),
                         fill="#111133", rx=2))
        # Simulated pixels
        for row in range(3):
            dwg.add(dwg.rect(insert=(x-W//2+7, y-H//2+7+row*9),
                             size=(W-14,6), fill="#2244cc", fill_opacity=0.6, rx=1))
        dwg.add(dwg.text("DISP", insert=(x,y+6),
                         font_size=9, fill="#aabbff",
                         font_family="monospace", text_anchor="middle"))

    def _sym_bmp280(self, dwg, x, y, comp):
        """BMP280 — IC negra 60×40 con pines I2C/SPI."""
        W, H = 60, 40
        dwg.add(dwg.rect(insert=(x-W//2, y-H//2), size=(W, H),
                         fill="#1a1a1a", stroke="#000000", stroke_width=1.8, rx=2))
        # Pin 1 marker
        dwg.add(dwg.circle(center=(x-W//2+5, y-H//2+5), r=1.5, fill="#cccccc"))
        # Left pins: VCC, GND
        for i, lbl in enumerate(("VCC", "GND")):
            py = y - 8 + i*16
            dwg.add(dwg.line(start=(x-W//2-10, py), end=(x-W//2, py),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
            dwg.add(dwg.text(lbl, insert=(x-W//2+3, py+3),
                             font_size=7, fill="#dddddd",
                             font_family="monospace", text_anchor="start"))
        # Right pins: SDA, SCL, CSB, SDO
        for i, lbl in enumerate(("SDA", "SCL", "CSB", "SDO")):
            py = y - 12 + i*8
            dwg.add(dwg.line(start=(x+W//2, py), end=(x+W//2+10, py),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
            dwg.add(dwg.text(lbl, insert=(x+W//2-3, py+3),
                             font_size=7, fill="#dddddd",
                             font_family="monospace", text_anchor="end"))
        # Labels
        dwg.add(dwg.text("BMP280", insert=(x, y-3),
                         font_size=9, fill="#ffffff",
                         font_family="monospace", font_weight="bold",
                         text_anchor="middle"))
        dwg.add(dwg.text("Temp/Press", insert=(x, y+9),
                         font_size=7, fill="#aaaaaa",
                         font_family="monospace", text_anchor="middle"))

    def _sym_oled(self, dwg, x, y, comp):
        """OLED 128×64 — rectángulo con pantalla interior y pines abajo."""
        W, H = 70, 50
        # Outer board (greenish PCB tone)
        dwg.add(dwg.rect(insert=(x-W//2, y-H//2), size=(W, H),
                         fill=self._FILL_DISP, stroke="#334499",
                         stroke_width=2, rx=3))
        # Inner screen area (azul oscuro)
        sx, sy, sw, sh = x-W//2+5, y-H//2+5, W-10, H-20
        dwg.add(dwg.rect(insert=(sx, sy), size=(sw, sh),
                         fill="#0a1030", stroke="#222244", stroke_width=1, rx=2))
        # Simulated pixel rows
        for row in range(3):
            dwg.add(dwg.rect(insert=(sx+3, sy+3+row*7),
                             size=(sw-6, 4), fill="#3366ff",
                             fill_opacity=0.55, rx=1))
        # Labels
        dwg.add(dwg.text("OLED", insert=(x, y+H//2-9),
                         font_size=8, fill="#ffffff",
                         font_family="monospace", font_weight="bold",
                         text_anchor="middle"))
        dwg.add(dwg.text("128x64", insert=(x, y+H//2-1),
                         font_size=7, fill="#aabbff",
                         font_family="monospace", text_anchor="middle"))
        # Bottom pins: GND, VCC, SCL, SDA
        pin_labels = ("GND", "VCC", "SCL", "SDA")
        spacing = W / (len(pin_labels) + 1)
        for i, lbl in enumerate(pin_labels):
            px = x - W//2 + spacing*(i+1)
            dwg.add(dwg.line(start=(px, y+H//2), end=(px, y+H//2+10),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
            dwg.add(dwg.text(lbl, insert=(px, y+H//2+18),
                             font_size=6, fill=self._TEXT_COLOR,
                             font_family="monospace", text_anchor="middle"))

    def _sym_ic_generic(self, dwg, x, y, comp):
        """Generic IC / driver."""
        W, H = 64, 42
        name = comp.get("name", comp.get("id","IC"))[:9]
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2), size=(W,H),
                         fill="#f0f0f8", stroke="#555566", stroke_width=1.8))
        dwg.add(dwg.text(name, insert=(x,y+4),
                         font_size=10, fill="#333355",
                         font_family="monospace", text_anchor="middle"))
        # Notch
        dwg.add(dwg.path(d=f"M {x-6} {y-H//2} Q {x} {y-H//2+6} {x+6} {y-H//2}",
                         fill="#ccccdd", stroke="#555566", stroke_width=0.8))

    def _sym_l298n(self, dwg, x, y, comp):
        """L298N dual H-bridge."""
        W, H = 74, 52
        name = comp.get("name","L298N")[:8]
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2), size=(W,H),
                         fill=self._FILL_DRIVER, stroke="#885500", stroke_width=1.8))
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2), size=(W,16),
                         fill="#885500", fill_opacity=0.15))
        dwg.add(dwg.text(name, insert=(x,y-H//2+12),
                         font_size=10, fill="#885500",
                         font_family="monospace", text_anchor="middle", font_weight="bold"))
        for i,lbl in enumerate(["IN1","IN2","EN"]):
            dwg.add(dwg.text(lbl, insert=(x-W//2+4,y-6+i*13),
                             font_size=7, fill="#555566", font_family="monospace"))
        for i,lbl in enumerate(["OUT1","OUT2"]):
            dwg.add(dwg.text(lbl, insert=(x+10,y+0+i*13),
                             font_size=7, fill="#885500", font_family="monospace"))

    def _sym_stepper_driver(self, dwg, x, y, comp):
        """DRV8825/A4988 stepper driver."""
        W, H = 58, 44
        name = (comp.get("name", comp.get("id","DRV")) or "")[:8]
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2), size=(W,H),
                         fill=self._FILL_SENSOR, stroke="#116611", stroke_width=1.8))
        dwg.add(dwg.text(name, insert=(x,y-5),
                         font_size=9, fill="#116611",
                         font_family="monospace", text_anchor="middle", font_weight="bold"))
        for i,lbl in enumerate(["STP","DIR","EN"]):
            dwg.add(dwg.text(lbl, insert=(x-W//2+3,y-H//2+18+i*11),
                             font_size=7, fill="#555566", font_family="monospace"))
        for i,lbl in enumerate(["A1","A2","B1","B2"]):
            dwg.add(dwg.text(lbl, insert=(x+W//2-16,y-H//2+12+i*9),
                             font_size=7, fill="#116611", font_family="monospace"))

    def _sym_regulator(self, dwg, x, y, comp):
        """TO-220 voltage regulator."""
        # Body
        dwg.add(dwg.rect(insert=(x-18,y-14), size=(36,28),
                         fill=self._FILL_POWER, stroke="#776600", stroke_width=1.8))
        # Heat tab
        dwg.add(dwg.rect(insert=(x-9,y-22), size=(18,10),
                         fill="#eeeedd", stroke="#776600", stroke_width=1.2))
        # 3 pins
        for dx in (-10,0,10):
            dwg.add(dwg.line(start=(x+dx,y+14), end=(x+dx,y+24),
                             stroke=self._PIN_COLOR, stroke_width=2.2))
        for dx,lbl in [(-14,"IN"),(0,"GND"),(14,"OUT")]:
            dwg.add(dwg.text(lbl, insert=(x+dx,y+34),
                             font_size=6, fill=self._TEXT_VAL,
                             font_family="monospace", text_anchor="middle"))
        name = (comp.get("name","REG") or "")[:8]
        dwg.add(dwg.text(name, insert=(x,y+5),
                         font_size=8, fill="#776600",
                         font_family="monospace", text_anchor="middle"))

    def _sym_moisture(self, dwg, x, y, comp):
        """FC-28 soil moisture sensor."""
        W, H = 30, 42
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2+10), size=(W,20),
                         fill=self._FILL_SENSOR, stroke="#117755", stroke_width=1.5, rx=2))
        dwg.add(dwg.text("FC28", insert=(x,y+8),
                         font_size=7, fill="#117755",
                         font_family="monospace", text_anchor="middle"))
        for dx in (-8,8):
            dwg.add(dwg.rect(insert=(x+dx-3,y+10), size=(6,20),
                             fill="#226633", stroke="#117755", stroke_width=1))
        for dx,lbl in [(-8,"A"),(0,"V"),(8,"G")]:
            dwg.add(dwg.line(start=(x+dx,y-H//2+10), end=(x+dx,y-H//2),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
            dwg.add(dwg.text(lbl, insert=(x+dx,y-H//2-3),
                             font_size=6, fill="#117755",
                             font_family="monospace", text_anchor="middle"))

    def _sym_ultrasonic(self, dwg, x, y, comp):
        """HC-SR04 ultrasonic sensor."""
        dwg.add(dwg.rect(insert=(x-32,y-17), size=(64,34),
                         fill=self._FILL_SENSOR, stroke="#227799", stroke_width=1.8, rx=3))
        for cx_,lbl in [(x-16,"T"),(x+16,"E")]:
            dwg.add(dwg.circle(center=(cx_,y), r=11,
                               fill="#ddeeff", stroke="#227799", stroke_width=1.5))
            dwg.add(dwg.text(lbl, insert=(cx_,y+4),
                             font_size=8, fill="#227799",
                             font_family="monospace", text_anchor="middle"))
        for r in (14,20):
            dwg.add(dwg.path(
                d=f"M {x+32} {y-r//2} Q {x+32+r//3} {y} {x+32} {y+r//2}",
                fill="none", stroke="#227799", stroke_width=1, stroke_opacity=0.6))

    def _sym_connector(self, dwg, x, y, comp):
        """Pin header / terminal block."""
        try:
            pins = int(comp.get("pins", comp.get("value", 2)) or 2)
        except (ValueError, TypeError):
            pins = 2
        pins = max(2, min(pins, 8))
        H, W = pins*11+6, 26
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2), size=(W,H),
                         fill="#f0f0f0", stroke="#555566", stroke_width=1.5, rx=2))
        for i in range(pins):
            py_ = y-H//2+8+i*11
            dwg.add(dwg.rect(insert=(x-W//2+3,py_-4), size=(10,8),
                             fill="#cccc88", stroke="#888866", stroke_width=0.8, rx=1))
            dwg.add(dwg.circle(center=(x-W//2+8,py_), r=2.5,
                               fill="#333300", stroke="none"))
            dwg.add(dwg.line(start=(x-W//2-10,py_), end=(x-W//2,py_),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
        dwg.add(dwg.text(f"J{pins}", insert=(x+8,y+4),
                         font_size=8, fill="#555566",
                         font_family="monospace", text_anchor="middle"))

    def _sym_rf_module(self, dwg, x, y, comp):
        """HC-05 / nRF24L01 RF module."""
        W, H = 60, 40
        name = (comp.get("name","RF") or "")[:8]
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2), size=(W,H),
                         fill=self._FILL_COMM, stroke="#660099", stroke_width=1.8, rx=3))
        # Antenna
        dwg.add(dwg.line(start=(x+W//2,y-H//4), end=(x+W//2+14,y-H//4),
                         stroke="#660099", stroke_width=2))
        dwg.add(dwg.line(start=(x+W//2+14,y-H//4-7), end=(x+W//2+14,y-H//4+7),
                         stroke="#660099", stroke_width=1.5))
        for r in (5,10):
            dwg.add(dwg.path(
                d=f"M {x+W//2+16} {y-H//4-r} Q {x+W//2+22+r} {y-H//4} {x+W//2+16} {y-H//4+r}",
                fill="none", stroke="#660099", stroke_width=1.2, stroke_opacity=0.7))
        dwg.add(dwg.text(name, insert=(x,y+5),
                         font_size=9, fill="#660099",
                         font_family="monospace", text_anchor="middle", font_weight="bold"))

    def _sym_converter(self, dwg, x, y, comp):
        """Buck/Boost DC-DC converter."""
        W, H = 62, 42
        is_boost = "boost" in (comp.get("resolved_type",comp.get("type","")) or "").lower()
        color = "#cc8800" if is_boost else "#0055aa"
        label = "BOOST↑" if is_boost else "BUCK↓"
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2), size=(W,H),
                         fill=self._FILL_POWER, stroke=color, stroke_width=1.8, rx=3))
        # Coil symbol
        cx0 = x-10
        for i in range(4):
            dwg.add(dwg.path(
                d=f"M {cx0+i*6} {y} Q {cx0+i*6+3} {y-10} {cx0+i*6+6} {y}",
                fill="none", stroke=color, stroke_width=1.8))
        dwg.add(dwg.text(label, insert=(x,y+16),
                         font_size=8, fill=color,
                         font_family="monospace", text_anchor="middle"))
        for x0,x1,lbl in [(x-W//2-10,x-W//2,"IN"),(x+W//2,x+W//2+10,"OUT")]:
            dwg.add(dwg.line(start=(x0,y), end=(x1,y),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
            dwg.add(dwg.text(lbl, insert=(x0-2 if lbl=="IN" else x1+2,y-5),
                             font_size=7, fill=color, font_family="monospace",
                             text_anchor="end" if lbl=="IN" else "start"))

    def _sym_stepper(self, dwg, x, y, comp):
        """Stepper motor — circle with 4 coil leads."""
        dwg.add(dwg.circle(center=(x,y), r=24,
                           fill=self._FILL_PASSIVE, stroke="#224488", stroke_width=2))
        dwg.add(dwg.text("STEP", insert=(x,y+6),
                         font_size=10, fill="#224488",
                         font_family="Arial", font_weight="bold", text_anchor="middle"))
        for ang_deg,lbl in [(45,"A+"),(135,"A-"),(225,"B+"),(315,"B-")]:
            rad = math.radians(ang_deg)
            ex, ey = x+24*math.cos(rad), y+24*math.sin(rad)
            lx, ly_ = x+36*math.cos(rad), y+36*math.sin(rad)
            dwg.add(dwg.line(start=(ex,ey), end=(lx,ly_),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
            dwg.add(dwg.text(lbl, insert=(x+42*math.cos(rad),y+42*math.sin(rad)+3),
                             font_size=7, fill="#224488",
                             font_family="monospace", text_anchor="middle"))

    def _sym_servo(self, dwg, x, y, comp):
        """Servo motor."""
        W, H = 48, 32
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2), size=(W,H),
                         fill=self._FILL_SENSOR, stroke="#226622", stroke_width=1.8, rx=4))
        dwg.add(dwg.circle(center=(x,y-H//2-9), r=8,
                           fill=self._FILL_PASSIVE, stroke="#226622", stroke_width=1.5))
        dwg.add(dwg.line(start=(x,y-H//2-9), end=(x+8,y-H//2-9),
                         stroke="#226622", stroke_width=2.5))
        dwg.add(dwg.text("SRV", insert=(x,y+6),
                         font_size=10, fill="#226622",
                         font_family="monospace", text_anchor="middle", font_weight="bold"))
        for dx,c in [(-9,"#ee2222"),(0,"#555555"),(9,"#dddd00")]:
            dwg.add(dwg.line(start=(x+dx,y+H//2), end=(x+dx,y+H//2+10),
                             stroke=c, stroke_width=2.5))

    def _sym_inductor(self, dwg, x, y, comp):
        """Inductor — 4 bumps."""
        bumps, bw = 4, 9
        total = bumps*bw
        x0 = x - total//2
        for i in range(bumps):
            cxb = x0+i*bw+bw//2
            dwg.add(dwg.path(
                d=f"M {x0+i*bw} {y} Q {cxb} {y-15} {x0+(i+1)*bw} {y}",
                fill="none", stroke=self._SYM_STROKE, stroke_width=2))
        for x0_,x1_ in [(x-total//2-15,x-total//2),(x+total//2,x+total//2+15)]:
            dwg.add(dwg.line(start=(x0_,y), end=(x1_,y),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
        val = comp.get("value","")
        if val:
            dwg.add(dwg.text(val, insert=(x,y+16),
                             font_size=8, fill=self._TEXT_VAL,
                             font_family="monospace", text_anchor="middle"))

    def _sym_battery(self, dwg, x, y, comp):
        """Battery — stacked cell plates."""
        for i,(w,thick) in enumerate([(22,2.5),(14,1.5),(22,2.5),(14,1.5)]):
            py_ = y-14+i*7
            dwg.add(dwg.line(start=(x-w//2,py_), end=(x+w//2,py_),
                             stroke="#117700", stroke_width=thick))
        for y0,y1 in [(y-14,y-24),(y+14,y+24)]:
            dwg.add(dwg.line(start=(x,y0), end=(x,y1),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
        dwg.add(dwg.text("+", insert=(x+16,y-18),
                         font_size=12, fill="#117700",
                         font_family="Arial", font_weight="bold"))
        val = comp.get("value","")
        if val:
            dwg.add(dwg.text(val, insert=(x,y+36),
                             font_size=8, fill="#117700",
                             font_family="monospace", text_anchor="middle"))

    def _sym_transformer(self, dwg, x, y, comp):
        """Transformer — EI-core with primary/secondary windings."""
        # Primary winding (left, 4 bumps)
        for i in range(4):
            cx0 = x - 28 + i * 8
            dwg.add(dwg.path(
                d=f"M {cx0} {y} Q {cx0+4} {y-14} {cx0+8} {y}",
                fill="none", stroke=self._SYM_STROKE, stroke_width=1.8))
        # Secondary winding (right, 4 bumps)
        for i in range(4):
            cx0 = x + 4 + i * 8
            dwg.add(dwg.path(
                d=f"M {cx0} {y} Q {cx0+4} {y-14} {cx0+8} {y}",
                fill="none", stroke=self._SYM_STROKE, stroke_width=1.8))
        # Core lines
        for dx in (-2, 2):
            dwg.add(dwg.line(start=(x+dx, y-16), end=(x+dx, y+2),
                             stroke="#553300", stroke_width=1.5))
        # Pin leads
        for x0, x1 in [(x-30, x-28), (x+36, x+38)]:
            dwg.add(dwg.line(start=(x0, y-10), end=(x1, y-10),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
            dwg.add(dwg.line(start=(x0, y+10), end=(x1, y+10),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
        # Labels
        dwg.add(dwg.text("P", insert=(x-32, y+4),
                         font_size=7, fill="#553300", font_family="Arial"))
        dwg.add(dwg.text("S", insert=(x+34, y+4),
                         font_size=7, fill="#553300", font_family="Arial"))

    def _sym_bridge_rectifier(self, dwg, x, y, comp):
        """Bridge rectifier — 4-diode diamond with AC in / DC out."""
        # Four diode triangles at diamond positions
        diodes = [
            # (tip, base_center, direction)
            ((x, y-14), (x, y-2),  "down"),   # top
            ((x, y+14), (x, y+2),  "up"),     # bottom
            ((x-14, y), (x-2, y),  "right"),  # left
            ((x+14, y), (x+2, y),  "left"),   # right
        ]
        for (tx,ty),(bx,by),d in diodes:
            if d == "down":
                pts = [(bx-8,by),(bx+8,by),(tx,ty)]
            elif d == "up":
                pts = [(bx-8,by),(bx+8,by),(tx,ty)]
            elif d == "right":
                pts = [(bx,by-8),(bx,by+8),(tx,ty)]
            else:
                pts = [(bx,by-8),(bx,by+8),(tx,ty)]
            dwg.add(dwg.polygon(pts, fill="#dddddd", fill_opacity=0.4,
                                stroke=self._SYM_STROKE, stroke_width=1.4))
        # AC input pins (left/right of diamond)
        for x0, lbl in [(x-28, "AC~"), (x+16, "AC~")]:
            dwg.add(dwg.line(start=(x0, y), end=(x0+12, y),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
            dwg.add(dwg.text(lbl, insert=(x0-2, y-3),
                             font_size=6, fill=self._TEXT_COLOR, font_family="monospace"))
        # DC output pins (top/bottom)
        for y0, lbl, col in [(y-28, "+", "#cc2222"), (y+18, "−", "#2244aa")]:
            dwg.add(dwg.line(start=(x, y0), end=(x, y0+12 if y0 < y else y0-12),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
            dwg.add(dwg.text(lbl, insert=(x+3, y0+4),
                             font_size=10, fill=col, font_family="Arial", font_weight="bold"))

    def _sym_fuse(self, dwg, x, y, comp):
        """Fuse — zigzag inside oval (IEC style)."""
        # Oval body
        dwg.add(dwg.ellipse(center=(x, y), r=(22, 9),
                            fill=self._FILL_PASSIVE, stroke=self._SYM_STROKE, stroke_width=1.6))
        # Zigzag element
        pts = [(x-14, y)]
        for i in range(7):
            pts.append((x-14+i*4+2, y + (6 if i % 2 == 0 else -6)))
        pts.append((x+14, y))
        for i in range(len(pts)-1):
            dwg.add(dwg.line(start=pts[i], end=pts[i+1],
                             stroke="#cc5500", stroke_width=1.4))
        # Lead wires
        for x0, x1 in [(x-34, x-22), (x+22, x+34)]:
            dwg.add(dwg.line(start=(x0, y), end=(x1, y),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
        val = comp.get("value", "")
        if val:
            dwg.add(dwg.text(val, insert=(x, y+18),
                             font_size=7, fill=self._TEXT_VAL,
                             font_family="monospace", text_anchor="middle"))

    def _sym_varistor(self, dwg, x, y, comp):
        """Varistor/MOV — resistor body + diagonal bidirectional arrow."""
        # Resistor body
        W, H = 30, 12
        dwg.add(dwg.rect(insert=(x-W//2, y-H//2), size=(W, H),
                         fill="#f5e8c8", stroke=self._SYM_STROKE, stroke_width=1.5))
        # Lead stubs
        for x0, x1 in [(x-W//2-12, x-W//2), (x+W//2, x+W//2+12)]:
            dwg.add(dwg.line(start=(x0, y), end=(x1, y),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
        # Diagonal arrow (bidirectional)
        dwg.add(dwg.line(start=(x-10, y+10), end=(x+10, y-10),
                         stroke="#cc6600", stroke_width=1.6))
        for tip, ang_off in [((x+10, y-10), 0.7), ((x-10, y+10), 0.7+math.pi)]:
            ang = math.atan2(-20, 20)
            for sign in [1, -1]:
                ex = tip[0] - 4*math.cos(ang + sign*ang_off*0.4)
                ey = tip[1] - 4*math.sin(ang + sign*ang_off*0.4)
                dwg.add(dwg.line(start=tip, end=(ex, ey),
                                 stroke="#cc6600", stroke_width=1.2))
        # V label
        dwg.add(dwg.text("V", insert=(x, y+4),
                         font_size=9, fill="#cc6600",
                         font_family="Arial", text_anchor="middle", font_weight="bold"))

    def _sym_mosfet_driver(self, dwg, x, y, comp):
        """Gate driver IC (IR2104, ULN2003, etc) — IC box with labelled pins."""
        W, H = 58, 44
        name = (comp.get("name", comp.get("id", "DRV")) or "")[:9]
        dwg.add(dwg.rect(insert=(x-W//2, y-H//2), size=(W, H),
                         fill=self._FILL_DRIVER, stroke="#663300", stroke_width=1.8))
        # Header bar
        dwg.add(dwg.rect(insert=(x-W//2, y-H//2), size=(W, 15),
                         fill="#663300", fill_opacity=0.15))
        dwg.add(dwg.text(name, insert=(x, y-H//2+11),
                         font_size=10, fill="#663300",
                         font_family="monospace", text_anchor="middle", font_weight="bold"))
        # Input pins (left)
        for i, lbl in enumerate(["IN", "EN", "VCC"]):
            py_ = y - 8 + i * 11
            dwg.add(dwg.line(start=(x-W//2-12, py_), end=(x-W//2, py_),
                             stroke=self._PIN_COLOR, stroke_width=1))
            dwg.add(dwg.text(lbl, insert=(x-W//2+3, py_+3),
                             font_size=6.5, fill="#555566", font_family="monospace"))
        # Output pins (right)
        for i, lbl in enumerate(["HO", "LO", "GND"]):
            py_ = y - 8 + i * 11
            dwg.add(dwg.line(start=(x+W//2, py_), end=(x+W//2+12, py_),
                             stroke=self._PIN_COLOR, stroke_width=1))
            dwg.add(dwg.text(lbl, insert=(x+W//2-16, py_+3),
                             font_size=6.5, fill="#885533", font_family="monospace"))

    def _sym_connector_ac(self, dwg, x, y, comp):
        """IEC AC connector — 3-pin (L/N/PE) with housing."""
        W, H = 28, 42
        dwg.add(dwg.rect(insert=(x-W//2, y-H//2), size=(W, H),
                         fill="#f0f0e8", stroke="#555566", stroke_width=1.8, rx=3))
        pins = [("L", "#cc2222"), ("N", "#2244cc"), ("PE", "#117700")]
        for i, (lbl, col) in enumerate(pins):
            py_ = y - H//2 + 8 + i * 14
            # Pin socket
            dwg.add(dwg.circle(center=(x, py_), r=4,
                               fill="#dddddd", stroke=col, stroke_width=1.5))
            dwg.add(dwg.circle(center=(x, py_), r=2,
                               fill="#111111", stroke="none"))
            # Wire stub
            dwg.add(dwg.line(start=(x-W//2-10, py_), end=(x-W//2, py_),
                             stroke=col, stroke_width=2))
            # Label
            dwg.add(dwg.text(lbl, insert=(x+W//2+3, py_+3),
                             font_size=7, fill=col, font_family="monospace"))


    def _sym_rtc(self, dwg, x, y, comp):
        """RTC module — IC box + coin cell symbol."""
        W, H = 52, 32
        name = comp.get("name", comp.get("id","RTC"))[:10]
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2), size=(W,H),
                         fill="#e8f0ff", stroke="#224488", stroke_width=1.8, rx=2))
        # Header bar
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2), size=(W,14),
                         fill="#224488", fill_opacity=0.15, rx=2))
        dwg.add(dwg.text("RTC", insert=(x,y-H//2+10),
                         font_size=9, fill="#224488",
                         font_family="monospace", text_anchor="middle", font_weight="bold"))
        dwg.add(dwg.text(name, insert=(x,y+8),
                         font_size=8, fill="#334455",
                         font_family="monospace", text_anchor="middle"))
        # Coin cell symbol (small circle on side)
        dwg.add(dwg.circle(center=(x+W//2+8,y), r=7,
                           fill="none", stroke="#888899", stroke_width=1.5))
        dwg.add(dwg.line(start=(x+W//2+12,y), end=(x+W//2+18,y),
                         stroke="#888899", stroke_width=1.2))
        # I2C pin stubs
        for sign, label in [(-1,"SDA"), (-1,"SCL"), (1,"VCC"), (1,"GND")]:
            yi = y - 8 + (0 if label in ("SDA","VCC") else 8)
            x_body = x + sign * W//2
            x_tip  = x + sign * (W//2 + 12)
            dwg.add(dwg.line(start=(x_body,yi), end=(x_tip,yi),
                             stroke=self._PIN_COLOR, stroke_width=1))
            dwg.add(dwg.text(label, insert=(x_tip + sign*4, yi+3),
                             font_size=6, fill="#667788",
                             font_family="monospace",
                             text_anchor="start" if sign > 0 else "end"))

    def _sym_generic(self, dwg, x, y, comp):
        """Fallback generic IC with named pin stubs from comp data."""
        # Infer pin list from component metadata
        raw_pins = comp.get("pins", [])
        if isinstance(raw_pins, list) and raw_pins:
            pin_names = [str(p.get("name", p) if isinstance(p, dict) else p)
                         for p in raw_pins]
        else:
            # Derive from nets: collect all pin labels for this component
            pin_names = []
            # Try to pull from name-based heuristics
            t = (comp.get("resolved_type", comp.get("type","")) or "").lower()
            if "i2c" in t or "bmp" in t or "sht" in t:
                pin_names = ["VCC", "GND", "SDA", "SCL"]
            elif "uart" in t:
                pin_names = ["VCC", "GND", "TX", "RX"]
            elif "spi" in t:
                pin_names = ["VCC", "GND", "MOSI", "MISO", "SCK", "CS"]
            else:
                pin_names = ["VCC", "GND", "IN", "OUT"]

        n_left  = (len(pin_names) + 1) // 2
        n_right = len(pin_names) - n_left
        n_max   = max(n_left, n_right, 2)
        W = 52
        H = max(34, n_max * 13 + 10)
        name = (comp.get("name", comp.get("id", "?")) or "")[:10]
        t_label = (comp.get("resolved_type", comp.get("type", "?")) or "")[:8]

        dwg.add(dwg.rect(insert=(x-W//2, y-H//2), size=(W, H),
                         fill="#f0f0f8", stroke="#6666aa", stroke_width=1.5, rx=2))
        # IC notch
        dwg.add(dwg.path(
            d=f"M {x-6} {y-H//2} Q {x} {y-H//2+6} {x+6} {y-H//2}",
            fill="#ccccdd", stroke="#6666aa", stroke_width=0.8))
        # Type label (small, top)
        dwg.add(dwg.text(t_label, insert=(x, y-H//2+12),
                         font_size=7, fill="#8888aa",
                         font_family="monospace", text_anchor="middle"))
        # Name label (center)
        dwg.add(dwg.text(name, insert=(x, y+5),
                         font_size=9, fill="#333355",
                         font_family="monospace", text_anchor="middle"))

        left_pins  = pin_names[:n_left]
        right_pins = pin_names[n_left:]

        # Left pins
        for i, lbl in enumerate(left_pins):
            py_ = y - (n_left - 1) * 6 + i * 12
            x_body = x - W//2
            x_tip  = x_body - 12
            dwg.add(dwg.line(start=(x_body, py_), end=(x_tip, py_),
                             stroke=self._PIN_COLOR, stroke_width=1))
            pin_col = ("#cc2222" if "VCC" in lbl or "VDD" in lbl
                       else "#2244aa" if "GND" in lbl
                       else self._TEXT_COLOR)
            dwg.add(dwg.text(lbl, insert=(x_body+3, py_+3),
                             font_size=6, fill=pin_col,
                             font_family="monospace"))
            dwg.add(dwg.text(str(i+1), insert=(x_tip-2, py_+3),
                             font_size=5.5, fill="#999999",
                             font_family="monospace", text_anchor="end"))

        # Right pins
        for i, lbl in enumerate(right_pins):
            py_ = y - (n_right - 1) * 6 + i * 12
            x_body = x + W//2
            x_tip  = x_body + 12
            dwg.add(dwg.line(start=(x_body, py_), end=(x_tip, py_),
                             stroke=self._PIN_COLOR, stroke_width=1))
            pin_col = ("#cc2222" if "VCC" in lbl or "VDD" in lbl
                       else "#2244aa" if "GND" in lbl
                       else self._TEXT_COLOR)
            dwg.add(dwg.text(lbl, insert=(x_body-3, py_+3),
                             font_size=6, fill=pin_col,
                             font_family="monospace", text_anchor="end"))
            dwg.add(dwg.text(str(n_left+i+1), insert=(x_tip+2, py_+3),
                             font_size=5.5, fill="#999999",
                             font_family="monospace"))


    # ── Legend ───────────────────────────────────────────────────────────────

    def _draw_legend(self, dwg, nets: List[Dict], width: int, height: int):
        if not nets:
            return
        inset = (BORDER_MM + ZONE_REF_MM) * _PX_PER_MM
        lx = int(width - inset - 195)
        ly = int(inset + 12)
        n  = min(len(nets), 9)
        dwg.add(dwg.rect(insert=(lx - 4, ly - 2), size=(190, n * 16 + 14),
                         fill="#fffffc", fill_opacity=0.92,
                         stroke="#aaaacc", stroke_width=1, rx=3))
        dwg.add(dwg.text("Nets", insert=(lx, ly + 9),
                         font_size=9, fill="#666688",
                         font_family="monospace", font_weight="bold"))
        for i, net in enumerate(nets[:n]):
            yy = ly + 22 + i * 15
            color = _net_color(net["name"])
            dwg.add(dwg.line(start=(lx, yy), end=(lx + 22, yy),
                             stroke=color, stroke_width=2.2))
            dwg.add(dwg.circle(center=(lx + 11, yy), r=2, fill=color))
            dwg.add(dwg.text(net["name"][:22], insert=(lx + 26, yy + 4),
                             font_size=9, fill=color, font_family="monospace"))
        if len(nets) > 9:
            dwg.add(dwg.text(f"… +{len(nets) - 9} redes",
                             insert=(lx, ly + 22 + 9 * 15),
                             font_size=8, fill="#888899", font_family="Arial"))

    def _draw_annotations(self, dwg, circuit_data: Dict, width: int, height: int):
        drc = circuit_data.get("drc", {})
        issues = drc.get("errors", [])
        if not issues:
            return
        # Anchor errors above the title block, on the left side
        inset = (BORDER_MM + ZONE_REF_MM) * _PX_PER_MM
        tb_top = height - inset - TITLE_BLOCK_H_MM * _PX_PER_MM
        for i, err in enumerate(issues[:3]):
            msg = f"⚠ {err.get('code', 'ERR')}: {err.get('message', '')}  "[:70]
            bw = len(msg) * 5 + 12
            yy = tb_top - 22 - i * 18
            dwg.add(dwg.rect(insert=(int(inset + 6), yy), size=(bw, 16),
                             fill="#fff8e0", stroke="#cc8800",
                             stroke_width=0.7, rx=2))
            dwg.add(dwg.text(msg, insert=(int(inset + 10), yy + 12),
                             font_size=9, fill="#885500", font_family="monospace"))
