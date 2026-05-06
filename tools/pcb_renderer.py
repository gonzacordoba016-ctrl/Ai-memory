# tools/pcb_renderer.py — facade. Real implementation lives in tools.eda.
#
# kicad_pcb_exporter still imports the 4 underscore-prefixed helpers below,
# so they are re-exported by name.

from tools.eda.pcb_draw import (
    PCBRenderer,
    _place_components,
    _route_traces,
    _board_size,
    _fp,
)

__all__ = [
    "PCBRenderer",
    "_place_components",
    "_route_traces",
    "_board_size",
    "_fp",
]
