"""
Stratum EDA Pipeline — wireado end-to-end determinista.

API de alto nivel para correr el pipeline completo IR → SVG/KiCad/BOM:

    from tools.eda.pipeline import run_pipeline, PipelineResult

    raw = Circuit(...)              # IR sin coords ni traces
    result = run_pipeline(raw)
    print(result.schematic_svg)
    print(result.pcb_svg)
    print(result.kicad_sch)
    print(result.kicad_pcb)
    print(result.bom_csv)
    for issue in result.drc_issues:
        print(issue.code, issue.message)

Etapas:
    1. validate_pre   → DRC sobre IR raw (errores estructurales).
    2. allocate_pins  → opcional (Fase 4) si hay PinRequest.
    3. place          → asigna Component.placement.
    4. route          → genera Circuit.traces + .vias.
    5. validate_post  → DRC final.
    6. render         → SVG schematic + PCB.
    7. export         → kicad_sch, kicad_pcb, BOM CSV.

Cada etapa es opcional vía flags. Por defecto corren todas.
"""
from __future__ import annotations

from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field

from tools.eda.constraint_engine import validate as run_validate
from tools.eda.export import export_kicad_pcb, export_kicad_sch, render_bom_csv
from tools.eda.ir import Circuit, ValidationIssue
from tools.eda.pin_allocator import PinRequest, allocate
from tools.eda.placement_engine import PlacementOptions, place
from tools.eda.render import (
    PCBRenderOptions,
    SchematicRenderOptions,
    render_pcb_svg,
    render_schematic_svg,
)
from tools.eda.routing_engine import RoutingOptions, route


class PipelineOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    pin_requests: list[PinRequest] = Field(default_factory=list)
    placement: PlacementOptions = Field(default_factory=PlacementOptions)
    routing: RoutingOptions = Field(default_factory=RoutingOptions)
    schematic: SchematicRenderOptions = Field(default_factory=SchematicRenderOptions)
    pcb: PCBRenderOptions = Field(default_factory=PCBRenderOptions)

    do_pre_drc: bool = True
    do_post_drc: bool = True
    do_render_schematic: bool = True
    do_render_pcb: bool = True
    do_export_kicad_sch: bool = True
    do_export_kicad_pcb: bool = True
    do_export_bom: bool = True


class PipelineResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    circuit: Circuit
    drc_pre: list[ValidationIssue] = Field(default_factory=list)
    drc_post: list[ValidationIssue] = Field(default_factory=list)
    pin_allocator_issues: list[ValidationIssue] = Field(default_factory=list)
    placement_issues: list[ValidationIssue] = Field(default_factory=list)
    routing_issues: list[ValidationIssue] = Field(default_factory=list)
    schematic_svg: str = ""
    pcb_svg: str = ""
    kicad_sch: str = ""
    kicad_pcb: str = ""
    bom_csv: str = ""

    @property
    def drc_issues(self) -> list[ValidationIssue]:
        return self.drc_pre + self.drc_post

    @property
    def all_issues(self) -> list[ValidationIssue]:
        return (self.drc_pre + self.pin_allocator_issues +
                self.placement_issues + self.routing_issues + self.drc_post)

    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.all_issues)


def run_pipeline(
    raw: Circuit,
    options: PipelineOptions | None = None,
) -> PipelineResult:
    options = options or PipelineOptions()
    out = PipelineResult(circuit=raw)
    circuit = raw

    if options.do_pre_drc:
        out.drc_pre = run_validate(circuit)

    if options.pin_requests:
        alloc = allocate(circuit, options.pin_requests)
        circuit = alloc.circuit
        out.pin_allocator_issues = alloc.issues

    placement = place(circuit, options.placement)
    circuit = placement.circuit
    out.placement_issues = placement.issues

    routing = route(circuit, options.routing)
    circuit = routing.circuit
    out.routing_issues = routing.issues

    if options.do_post_drc:
        out.drc_post = run_validate(circuit)

    out.circuit = circuit

    if options.do_render_schematic:
        out.schematic_svg = render_schematic_svg(circuit, options.schematic)
    if options.do_render_pcb:
        out.pcb_svg = render_pcb_svg(circuit, options.pcb)

    if options.do_export_kicad_sch:
        title = circuit.metadata.title or "Schematic"
        out.kicad_sch = export_kicad_sch(circuit, title=title)
    if options.do_export_kicad_pcb:
        out.kicad_pcb = export_kicad_pcb(circuit)
    if options.do_export_bom:
        out.bom_csv = render_bom_csv(circuit)

    return out
