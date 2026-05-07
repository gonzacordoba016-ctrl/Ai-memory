"""
BOM exporter — IR → CSV agrupado.

Agrupa por (type, value, footprint) y lista los refs unidos.
"""
from __future__ import annotations

import csv
import io

from pydantic import BaseModel, ConfigDict

from tools.eda.component_registry import get_registry
from tools.eda.ir import Circuit


class BOMRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    references: list[str]
    quantity: int
    type: str
    value: str
    footprint: str


def render_bom(circuit: Circuit) -> list[BOMRow]:
    """Agrupa los componentes por (type, value, footprint)."""
    registry = get_registry()
    groups: dict[tuple[str, str, str], list[str]] = {}
    for c in circuit.components:
        spec = registry.get(c.type)
        fp = spec.footprint_full_id if spec else ""
        key = (c.type, c.value or "", fp)
        groups.setdefault(key, []).append(c.ref)

    rows: list[BOMRow] = []
    for (t, v, fp), refs in sorted(groups.items()):
        rows.append(BOMRow(
            references=sorted(refs),
            quantity=len(refs),
            type=t,
            value=v,
            footprint=fp,
        ))
    return rows


def render_bom_csv(circuit: Circuit) -> str:
    rows = render_bom(circuit)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["References", "Quantity", "Type", "Value", "Footprint"])
    for r in rows:
        w.writerow([",".join(r.references), r.quantity, r.type, r.value,
                     r.footprint])
    return buf.getvalue()
