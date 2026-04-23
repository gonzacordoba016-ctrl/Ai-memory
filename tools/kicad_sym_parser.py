# tools/kicad_sym_parser.py — Parser de S-expressions KiCad .kicad_sym
#
# KiCad coordinate system: 1 unit = 1 mm, Y increases upward.
# SVG coordinate system: Y increases downward.
# Conversion: svg_x = kicad_x * SCALE, svg_y = -kicad_y * SCALE
#
# Each .kicad_sym file (new per-symbol format) contains:
#   (kicad_symbol_lib ... (symbol "NAME" ... (symbol "NAME_0_1" <drawing>) (symbol "NAME_1_1" <pins>) ...))

import os
import math
import re
from typing import Any, List, Optional, Tuple

SCALE = 10.0  # px per mm

SYM_DIR = os.path.join(os.path.dirname(__file__), "kicad_symbols")


# ─── S-expression tokenizer/parser ──────────────────────────────────────────

def _tokenize(text: str) -> List[str]:
    tokens = []
    i = 0
    while i < len(text):
        c = text[i]
        if c in ' \t\r\n':
            i += 1
        elif c == '(':
            tokens.append('(')
            i += 1
        elif c == ')':
            tokens.append(')')
            i += 1
        elif c == '"':
            j = i + 1
            while j < len(text) and text[j] != '"':
                if text[j] == '\\':
                    j += 1
                j += 1
            tokens.append(text[i:j+1])
            i = j + 1
        else:
            j = i
            while j < len(text) and text[j] not in ' \t\r\n()\"':
                j += 1
            tokens.append(text[i:j])
            i = j
    return tokens


def _parse_expr(tokens: List[str], pos: int) -> Tuple[Any, int]:
    """Parse one S-expression starting at tokens[pos]. Returns (value, next_pos)."""
    if tokens[pos] == '(':
        pos += 1  # consume '('
        result = []
        while tokens[pos] != ')':
            val, pos = _parse_expr(tokens, pos)
            result.append(val)
        pos += 1  # consume ')'
        return result, pos
    else:
        tok = tokens[pos]
        # Strip quotes
        if tok.startswith('"') and tok.endswith('"'):
            return tok[1:-1], pos + 1
        # Try numeric
        try:
            return float(tok), pos + 1
        except ValueError:
            return tok, pos + 1


def parse_sexp(text: str) -> Any:
    tokens = _tokenize(text)
    result, _ = _parse_expr(tokens, 0)
    return result


# ─── Primitive extraction ─────────────────────────────────────────────────────

def _find_all(sexp: list, tag: str) -> List[list]:
    """Recursively find all sub-lists starting with `tag`."""
    results = []
    if isinstance(sexp, list) and sexp:
        if sexp[0] == tag:
            results.append(sexp)
        for item in sexp[1:]:
            if isinstance(item, list):
                results.extend(_find_all(item, tag))
    return results


def _get(sexp: list, tag: str) -> Optional[list]:
    for item in sexp[1:]:
        if isinstance(item, list) and item and item[0] == tag:
            return item
    return None


def _num(sexp: list, tag: str, default: float = 0.0) -> float:
    node = _get(sexp, tag)
    if node and len(node) > 1:
        try:
            return float(node[1])
        except (ValueError, TypeError):
            pass
    return default


def _xy(expr: list) -> Optional[Tuple[float, float]]:
    if isinstance(expr, list) and len(expr) >= 3 and expr[0] == 'xy':
        return float(expr[1]), float(expr[2])
    return None


# Convert KiCad (x,y) → SVG (sx, sy) centered at origin
def _ksvg(kx: float, ky: float) -> Tuple[float, float]:
    return kx * SCALE, -ky * SCALE


# ─── Main extractor ───────────────────────────────────────────────────────────

def _extract_drawing(sexp: list) -> dict:
    """
    Extract all drawing primitives and pins from a symbol S-expression.
    Returns:
      {
        "rects":     [(x,y,w,h,style), ...],
        "polylines": [[(x,y), ...], ...],
        "circles":   [(cx,cy,r), ...],
        "arcs":      [{"start":(x,y),"mid":(x,y),"end":(x,y)}, ...],
        "pins":      [{"at":(x,y),"angle":a,"length":l,"name":n,"number":k}, ...],
        "bbox":      (x_min,y_min,x_max,y_max),
      }
    """
    rects = []
    polylines = []
    circles = []
    arcs = []
    pins = []

    # Walk all sub-expressions for drawing primitives
    def walk(node):
        if not isinstance(node, list) or not node:
            return
        tag = node[0]

        if tag == 'rectangle':
            start = _get(node, 'start')
            end   = _get(node, 'end')
            if start and end:
                sx, sy = _ksvg(float(start[1]), float(start[2]))
                ex, ey = _ksvg(float(end[1]),   float(end[2]))
                x = min(sx, ex)
                y = min(sy, ey)
                w = abs(ex - sx)
                h = abs(ey - sy)
                rects.append((x, y, w, h))

        elif tag == 'polyline':
            pts_node = _get(node, 'pts')
            if pts_node:
                pts = []
                for item in pts_node[1:]:
                    p = _xy(item)
                    if p:
                        pts.append(_ksvg(*p))
                if len(pts) >= 2:
                    polylines.append(pts)

        elif tag == 'circle':
            center = _get(node, 'center')
            radius = _get(node, 'radius')
            if center and radius:
                cx, cy = _ksvg(float(center[1]), float(center[2]))
                r = float(radius[1]) * SCALE
                circles.append((cx, cy, r))

        elif tag == 'arc':
            start_n = _get(node, 'start')
            mid_n   = _get(node, 'mid')
            end_n   = _get(node, 'end')
            if start_n and mid_n and end_n:
                arcs.append({
                    'start': _ksvg(float(start_n[1]), float(start_n[2])),
                    'mid':   _ksvg(float(mid_n[1]),   float(mid_n[2])),
                    'end':   _ksvg(float(end_n[1]),   float(end_n[2])),
                })

        elif tag == 'pin':
            at_node = _get(node, 'at')
            len_node = _get(node, 'length')
            name_node = _get(node, 'name')
            num_node  = _get(node, 'number')
            if at_node and len(at_node) >= 4:
                px, py = _ksvg(float(at_node[1]), float(at_node[2]))
                angle  = float(at_node[3])
                length = float(len_node[1]) * SCALE if len_node else SCALE
                pin_name   = name_node[1]  if (name_node and len(name_node) > 1) else ""
                pin_number = num_node[1]   if (num_node and len(num_node) > 1)  else ""
                pins.append({
                    'at': (px, py),
                    'angle': angle,
                    'length': length,
                    'name': pin_name,
                    'number': str(pin_number),
                })

        for child in node[1:]:
            if isinstance(child, list):
                walk(child)

    walk(sexp)

    # Bounding box from all coordinates
    all_x = []
    all_y = []
    for x, y, w, h in rects:
        all_x += [x, x+w]
        all_y += [y, y+h]
    for pts in polylines:
        for px, py in pts:
            all_x.append(px)
            all_y.append(py)
    for cx, cy, r in circles:
        all_x += [cx-r, cx+r]
        all_y += [cy-r, cy+r]
    for arc in arcs:
        for pt in (arc['start'], arc['mid'], arc['end']):
            all_x.append(pt[0])
            all_y.append(pt[1])
    for pin in pins:
        all_x.append(pin['at'][0])
        all_y.append(pin['at'][1])

    if all_x and all_y:
        bbox = (min(all_x), min(all_y), max(all_x), max(all_y))
    else:
        bbox = (-20, -20, 20, 20)

    return {
        'rects': rects,
        'polylines': polylines,
        'circles': circles,
        'arcs': arcs,
        'pins': pins,
        'bbox': bbox,
    }


# ─── Public API ───────────────────────────────────────────────────────────────

def load_symbol(local_name: str) -> Optional[dict]:
    """
    Load and parse a .kicad_sym file from tools/kicad_symbols/{local_name}.kicad_sym.
    Returns drawing dict or None if file not found.
    """
    path = os.path.join(SYM_DIR, f"{local_name}.kicad_sym")
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
        sexp = parse_sexp(text)
        return _extract_drawing(sexp)
    except Exception:
        return None
