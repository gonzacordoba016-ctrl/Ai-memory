"""
Golden tests visuales — pipeline determinista sobre fixtures canónicas.

Compara nets, pin assignments, placement, traces, SVG y exports KiCad
contra snapshots. Si cambia algo, el test falla y obliga a revisar la
diff antes de actualizar el snapshot.

Snapshots almacenados en `tests/golden/snapshots/<fixture>.json` (auto-
creados en el primer run). Para regenerar tras un cambio intencional,
borrar el JSON y correr el test.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools.eda.constraint_engine import run_drc
from tools.eda.export import export_kicad_pcb, export_kicad_sch, render_bom_csv
from tools.eda.placement_engine import place
from tools.eda.render import render_pcb_svg, render_schematic_svg
from tools.eda.routing_engine import route

from _golden_fixtures import ALL_FIXTURES


SNAPSHOTS_DIR = Path(__file__).parent / "golden_snapshots"
SNAPSHOTS_DIR.mkdir(exist_ok=True)


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _run_pipeline(fixture_fn) -> dict:
    """Corre pipeline completo y devuelve un dict de outputs serializables."""
    raw = fixture_fn()

    # 1. DRC sobre el IR raw.
    drc_raw = run_drc(raw)

    # 2. Place.
    place_result = place(raw)
    placed = place_result.circuit

    # 3. Route.
    route_result = route(placed)
    routed = route_result.circuit

    # 4. DRC final.
    drc_final = run_drc(routed)

    # 5. Render.
    sch_svg = render_schematic_svg(routed)
    pcb_svg = render_pcb_svg(routed)

    # 6. Export.
    sch_kicad = export_kicad_sch(routed)
    pcb_kicad = export_kicad_pcb(routed)
    bom_csv = render_bom_csv(routed)

    # 7. Diagnostics — qué importa para el snapshot.
    return {
        # IR estructural.
        "components": [
            {"ref": c.ref, "type": c.type, "value": c.value,
             "placement": (
                 {"x": round(c.placement.position.x, 3),
                  "y": round(c.placement.position.y, 3),
                  "rotation": c.placement.rotation_deg,
                  "side": c.placement.side.value}
                 if c.placement else None
             )}
            for c in sorted(routed.components, key=lambda c: c.ref)
        ],
        "nets": [
            {"name": n.name, "class": n.net_class,
             "nodes": sorted([f"{nd.ref}.{nd.pin}" for nd in n.nodes])}
            for n in sorted(routed.nets, key=lambda n: n.name)
        ],
        "traces_summary": {
            "count": len(routed.traces),
            "by_layer": {
                ly.value: sum(1 for t in routed.traces if t.layer == ly)
                for ly in {t.layer for t in routed.traces}
            },
            "by_net": {
                name: sum(1 for t in routed.traces if t.net == name)
                for name in sorted({t.net for t in routed.traces})
            },
        },
        "vias_summary": {
            "count": len(routed.vias),
            "by_net": {
                name: sum(1 for v in routed.vias if v.net == name)
                for name in sorted({v.net for v in routed.vias})
            },
        },
        "drc_raw_summary": _drc_summary(drc_raw),
        "drc_final_summary": _drc_summary(drc_final),
        "zones": place_result.zone_assignments,
        "board": (
            {"width_mm": round(routed.board.width_mm, 2),
             "height_mm": round(routed.board.height_mm, 2)}
            if routed.board else None
        ),
        # Hashes de outputs grandes — detectan cualquier cambio sin
        # almacenar megas de SVG/KiCad en el repo.
        "hashes": {
            "schematic_svg": _hash(sch_svg),
            "pcb_svg":       _hash(pcb_svg),
            "kicad_sch":     _hash(sch_kicad),
            "kicad_pcb":     _hash(pcb_kicad),
            "bom_csv":       _hash(bom_csv),
        },
        "byte_lengths": {
            "schematic_svg": len(sch_svg),
            "pcb_svg":       len(pcb_svg),
            "kicad_sch":     len(sch_kicad),
            "kicad_pcb":     len(pcb_kicad),
            "bom_csv":       len(bom_csv),
        },
    }


def _drc_summary(drc: dict) -> dict:
    return {
        "errors":   sorted([i["code"] for i in drc["errors"]]),
        "warnings": sorted([i["code"] for i in drc["warnings"]]),
        "info":     sorted([i["code"] for i in drc["info"]]),
        "total":    len(drc["issues"]),
    }


@pytest.mark.parametrize("fixture_name", sorted(ALL_FIXTURES))
def test_pipeline_matches_snapshot(fixture_name: str):
    fixture_fn = ALL_FIXTURES[fixture_name]
    actual = _run_pipeline(fixture_fn)
    snapshot_path = SNAPSHOTS_DIR / f"{fixture_name}.json"

    if not snapshot_path.exists():
        # Primer run: crear snapshot.
        snapshot_path.write_text(
            json.dumps(actual, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        pytest.skip(f"Snapshot creado: {snapshot_path.name}")
        return

    expected = json.loads(snapshot_path.read_text(encoding="utf-8"))

    # Comparación campo por campo para mensajes de error útiles.
    for key in ("components", "nets", "traces_summary", "vias_summary",
                "drc_raw_summary", "drc_final_summary", "zones", "board",
                "hashes", "byte_lengths"):
        assert actual[key] == expected[key], (
            f"[{fixture_name}] mismatch en '{key}'.\n"
            f"actual:   {json.dumps(actual[key], sort_keys=True)[:500]}\n"
            f"expected: {json.dumps(expected[key], sort_keys=True)[:500]}\n"
            f"Si el cambio es intencional, borrá tests/golden/snapshots/"
            f"{fixture_name}.json y re-corré los tests."
        )


@pytest.mark.parametrize("fixture_name", sorted(ALL_FIXTURES))
def test_pipeline_idempotent(fixture_name: str):
    """Pipeline corrido dos veces da exactamente el mismo output."""
    fixture_fn = ALL_FIXTURES[fixture_name]
    a = _run_pipeline(fixture_fn)
    b = _run_pipeline(fixture_fn)
    assert a == b


@pytest.mark.parametrize("fixture_name", sorted(ALL_FIXTURES))
def test_drc_final_no_pin_errors(fixture_name: str):
    """Después del pipeline, no debe haber errores de pin (forbidden/invalid)."""
    fixture_fn = ALL_FIXTURES[fixture_name]
    actual = _run_pipeline(fixture_fn)
    forbidden_codes = {"PIN_INVALID", "PIN_FORBIDDEN", "PIN_INPUT_ONLY_MISUSE"}
    errors = set(actual["drc_final_summary"]["errors"])
    intersection = errors & forbidden_codes
    assert not intersection, (
        f"[{fixture_name}] errores de pin que deberían atrapar place/route: "
        f"{intersection}"
    )
