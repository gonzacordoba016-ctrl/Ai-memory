"""SVG builder mínimo — strings inmutables, sin estado global.

Salida byte-determinista para tests. Sin escapes mágicos: el caller es
responsable de pasar texto seguro.
"""
from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr


def _attrs(attrs: dict) -> str:
    """Render atributos en orden alfabético para determinismo."""
    parts = []
    for k in sorted(attrs):
        v = attrs[k]
        if v is None:
            continue
        parts.append(f"{k}={quoteattr(str(v))}")
    return (" " + " ".join(parts)) if parts else ""


def tag(name: str, attrs: dict | None = None,
        children: str = "", *, self_closing: bool = False) -> str:
    """Render una etiqueta XML. `children` ya debe ser SVG válido."""
    a = _attrs(attrs or {})
    if self_closing and not children:
        return f"<{name}{a}/>"
    return f"<{name}{a}>{children}</{name}>"


def svg_root(width_mm: float, height_mm: float, body: str,
             *, view_box: str | None = None) -> str:
    vb = view_box or f"0 0 {width_mm} {height_mm}"
    attrs = {
        "xmlns": "http://www.w3.org/2000/svg",
        "width": f"{width_mm}mm",
        "height": f"{height_mm}mm",
        "viewBox": vb,
    }
    return f'<?xml version="1.0" encoding="UTF-8"?>\n' + tag("svg", attrs, body)


def rect(x: float, y: float, w: float, h: float, **attrs) -> str:
    a = {"x": x, "y": y, "width": w, "height": h, **attrs}
    return tag("rect", a, self_closing=True)


def line(x1: float, y1: float, x2: float, y2: float, **attrs) -> str:
    a = {"x1": x1, "y1": y1, "x2": x2, "y2": y2, **attrs}
    return tag("line", a, self_closing=True)


def polyline(points: list[tuple[float, float]], **attrs) -> str:
    pts = " ".join(f"{x},{y}" for x, y in points)
    a = {"points": pts, "fill": "none", **attrs}
    return tag("polyline", a, self_closing=True)


def circle(cx: float, cy: float, r: float, **attrs) -> str:
    a = {"cx": cx, "cy": cy, "r": r, **attrs}
    return tag("circle", a, self_closing=True)


def text(x: float, y: float, content: str, **attrs) -> str:
    a = {"x": x, "y": y, **attrs}
    return tag("text", a, escape(content))


def group(children: str, **attrs) -> str:
    return tag("g", attrs, children)


def style(css: str) -> str:
    return tag("style", {}, f"<![CDATA[{css}]]>")


def defs(children: str) -> str:
    return tag("defs", {}, children)


def fmt_num(n: float, decimals: int = 3) -> str:
    """Formato numérico determinista — strip de zeros trailing."""
    s = f"{n:.{decimals}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s if s else "0"
