"""
Renderers puros — consumen Circuit IR ya con placement + traces + vías
y emiten SVG. NO toman decisiones de placement, routing, ni infieren nets.

Reemplazan progresivamente:
    - tools/eda/symbol_draw.py  (legacy SchematicRenderer)
    - tools/eda/pcb_draw.py     (legacy PCBRenderer)

Mientras dure la compat, los legacy siguen accesibles vía
`tools/schematic_renderer.py` y `tools/pcb_renderer.py` (facades).
"""

from .schematic import render_schematic_svg, SchematicRenderOptions
from .pcb import render_pcb_svg, PCBRenderOptions

__all__ = [
    "render_schematic_svg",
    "render_pcb_svg",
    "SchematicRenderOptions",
    "PCBRenderOptions",
]
