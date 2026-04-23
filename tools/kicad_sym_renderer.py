# tools/kicad_sym_renderer.py — Render KiCad symbols as SVG primitives

import math
from typing import Dict, List, Optional, Tuple

from tools.kicad_sym_parser import load_symbol

# ─── Symbol cache ─────────────────────────────────────────────────────────────

_cache: Dict[str, Optional[dict]] = {}

def _load(local_name: str) -> Optional[dict]:
    if local_name not in _cache:
        _cache[local_name] = load_symbol(local_name)
    return _cache[local_name]


# ─── Map component type → local symbol file name ──────────────────────────────

SYMBOL_MAP = {
    "resistor":               "Device__R",
    "capacitor":              "Device__C",
    "capacitor_electrolytic": "Device__C_Polarized",
    "inductor":               "Device__L",
    "diode":                  "Device__D",
    "1n4007":                 "Device__D",
    "1n5819":                 "Device__D",
    "1n4148":                 "Device__D",
    "zener":                  "Device__D",
    "led":                    "Device__LED",
    "led_rgb":                "Device__LED",
    "battery":                "Device__Battery_Cell",
    "battery_18650":          "Device__Battery_Cell",
    "lipo":                   "Device__Battery_Cell",
    # Transistor/MOSFET: KiCad community symbols use `extends` from a
    # built-in base — they have no drawing primitives. Use hand-drawn fallback.
    "esp32":                  "MCU__ESP32",
    "esp8266":                "MCU__ESP8266",
    "rtc":                    "RTC__DS3231",
    "ds3231":                 "RTC__DS3231",
    "ds1307":                 "RTC__DS1307",
    "pcf8523":                "RTC__DS1307",
}

# Target bounding box (px) for each category
TARGET: Dict[str, Tuple[float, float]] = {
    "Device__R":            (28,  60),
    "Device__C":            (28,  56),
    "Device__C_Polarized":  (28,  56),
    "Device__L":            (28,  60),
    "Device__D":            (36,  60),
    "Device__LED":          (40,  70),
    "Device__Battery_Cell": (28,  60),
    "BJT__NPN":             (60,  60),
    "FET__NMOS":            (60,  60),
    "MCU__ESP32":           (90,  80),
    "MCU__ESP8266":         (90,  80),
    "RTC__DS3231":          (70,  60),
    "RTC__DS1307":          (70,  60),
}
DEFAULT_TARGET = (70, 70)


# ─── Colors (EDA light theme) ─────────────────────────────────────────────────

STROKE   = "#1a1a2e"
STROKE_W = 1.6
PIN_COLOR = "#1a1a2e"
PIN_W     = 1.3
FILL_PASSIVE = "#ffffff"
FILL_LED     = "#fffce0"
FILL_BJT     = "#f8f8ff"
FILL_FET     = "#f8f8ff"
FILL_MCU     = "#e8f0ff"
FILL_RTC     = "#e8f0ff"


def _fill_for(local_name: str) -> str:
    if "LED" in local_name:
        return FILL_LED
    if "BJT" in local_name or "FET" in local_name:
        return FILL_BJT
    if "MCU" in local_name:
        return FILL_MCU
    if "RTC" in local_name:
        return FILL_RTC
    return FILL_PASSIVE


# ─── Arc helper ──────────────────────────────────────────────────────────────

def _arc_path(start: Tuple, mid: Tuple, end: Tuple) -> str:
    """Compute SVG arc path from 3 points. Uses large_arc=0, sweep=1."""
    sx, sy = start
    mx, my = mid
    ex, ey = end

    # Find circle through 3 points
    ax, ay = sx - ex, sy - ey
    bx, by = mx - ex, my - ey
    D = 2 * (ax * by - ay * bx)
    if abs(D) < 1e-6:
        return f"M {sx:.2f} {sy:.2f} L {ex:.2f} {ey:.2f}"

    ux = (by * (ax*ax + ay*ay) - ay * (bx*bx + by*by)) / D
    uy = (ax * (bx*bx + by*by) - bx * (ax*ax + ay*ay)) / D
    cx = ex + ux
    cy = ey + uy
    r  = math.hypot(sx - cx, sy - cy)

    # Determine large_arc and sweep flags
    def cross2(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])

    sweep = 1 if cross2(start, mid, end) < 0 else 0
    dx_sm = sx - mx
    dy_sm = sy - my
    dx_me = mx - ex
    dy_me = my - ey
    # Approximate arc angle
    angle_total = math.atan2(ey-cy, ex-cx) - math.atan2(sy-cy, sx-cx)
    large_arc = 1 if abs(angle_total) > math.pi else 0

    return (f"M {sx:.2f} {sy:.2f} "
            f"A {r:.2f} {r:.2f} 0 {large_arc} {sweep} {ex:.2f} {ey:.2f}")


# ─── KiCadSymRenderer ────────────────────────────────────────────────────────

class KiCadSymRenderer:

    def get_local_name(self, comp_type: str) -> Optional[str]:
        return SYMBOL_MAP.get(comp_type.lower())

    def render(self, dwg, cx: float, cy: float, comp_type: str) -> bool:
        """
        Draw the KiCad symbol for comp_type centered at (cx, cy) in the svgwrite drawing.
        Returns True if rendered, False if no symbol available (use fallback).
        """
        local_name = self.get_local_name(comp_type)
        if not local_name:
            return False
        data = _load(local_name)
        if not data:
            return False

        # Reject symbols with no drawing primitives (uses `extends` — no geometry)
        has_draw = (data['rects'] or data['polylines'] or data['circles']
                    or data['arcs'])
        if not has_draw:
            return False

        bbox = data['bbox']
        bx_min, by_min, bx_max, by_max = bbox
        nbw = bx_max - bx_min  # natural bbox width (SVG px)
        nbh = by_max - by_min  # natural bbox height (SVG px)
        if nbw < 1 or nbh < 1:
            return False

        tw, th = TARGET.get(local_name, DEFAULT_TARGET)
        fs = min(tw / nbw, th / nbh)
        # Center of natural bbox
        ncx = (bx_min + bx_max) / 2
        ncy = (by_min + by_max) / 2

        def T(nx: float, ny: float) -> Tuple[float, float]:
            return cx + (nx - ncx) * fs, cy + (ny - ncy) * fs

        fill = _fill_for(local_name)

        # Draw rectangles
        for rx, ry, rw, rh in data['rects']:
            tx, ty = T(rx, ry)
            dwg.add(dwg.rect(
                insert=(tx, ty),
                size=(rw * fs, rh * fs),
                fill=fill,
                stroke=STROKE,
                stroke_width=STROKE_W,
            ))

        # Draw polylines
        for pts in data['polylines']:
            tpts = [T(px, py) for px, py in pts]
            dwg.add(dwg.polyline(
                points=tpts,
                fill="none",
                stroke=STROKE,
                stroke_width=STROKE_W,
            ))

        # Draw circles
        for ocx, ocy, r in data['circles']:
            tx, ty = T(ocx, ocy)
            dwg.add(dwg.circle(
                center=(tx, ty),
                r=r * fs,
                fill=fill,
                stroke=STROKE,
                stroke_width=STROKE_W,
            ))

        # Draw arcs
        for arc in data['arcs']:
            ts = T(*arc['start'])
            tm = T(*arc['mid'])
            te = T(*arc['end'])
            d = _arc_path(ts, tm, te)
            dwg.add(dwg.path(
                d=d,
                fill="none",
                stroke=STROKE,
                stroke_width=STROKE_W,
            ))

        # Draw pin stubs
        for pin in data['pins']:
            px, py = pin['at']
            angle_deg = pin['angle']
            length    = pin['length']
            angle_rad = math.radians(angle_deg)

            # Wire end (connection point) in natural coords → transformed
            tx, ty = T(px, py)

            # Body end: px + length*cos(a), py - length*sin(a) (Y-flipped)
            bex = px + length * math.cos(angle_rad)
            bey = py - length * math.sin(angle_rad)
            tbx, tby = T(bex, bey)

            # Draw stub from wire end to body end
            dwg.add(dwg.line(
                start=(tx, ty),
                end=(tbx, tby),
                stroke=PIN_COLOR,
                stroke_width=PIN_W,
            ))

            # Small pin number (inside body)
            num = pin.get('number', '')
            if num:
                # Label at body-side, small
                label_x = tbx + (tx - tbx) * 0.3
                label_y = tby + (ty - tby) * 0.3
                dwg.add(dwg.text(
                    str(num),
                    insert=(label_x, label_y + 3),
                    font_size=5,
                    fill="#888899",
                    font_family="monospace",
                    text_anchor="middle",
                ))

        return True
