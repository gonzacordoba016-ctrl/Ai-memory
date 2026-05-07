"""
Exporters desacoplados — consumen Circuit IR. No reinterpretan circuitos.

    - kicad_sch.py  — IR → .kicad_sch (S-expression)
    - kicad_pcb.py  — IR → .kicad_pcb
    - bom.py        — IR → CSV BOM agrupado

Reemplazan progresivamente:
    - tools/kicad_exporter.py
    - tools/kicad_pcb_exporter.py
    - tools/bom_generator.py

Mientras dure la compat, los legacy siguen accesibles.
"""

from .bom import BOMRow, render_bom_csv
from .kicad_pcb import export_kicad_pcb
from .kicad_sch import export_kicad_sch

__all__ = [
    "BOMRow",
    "export_kicad_pcb",
    "export_kicad_sch",
    "render_bom_csv",
]
