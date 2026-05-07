"""Modelos pydantic v2 del Circuit IR."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .types import (
    ElectricalType,
    Layer,
    NetName,
    PinId,
    RefId,
    Severity,
    Side,
    Vec2,
)


# ────────────────────────────────────────────────────────────────────────────
# Pin / Symbol / Footprint
# ────────────────────────────────────────────────────────────────────────────


class Pin(BaseModel):
    """Pin individual de un componente."""
    model_config = ConfigDict(extra="forbid")

    number: PinId
    name: str
    electrical_type: ElectricalType = ElectricalType.UNSPECIFIED
    # Funciones que este pin puede cumplir (I2C_SDA, ADC, PWM, GPIO, UART_TX, ...).
    # Lo usa el pin allocator para matchear capabilities.
    functions: list[str] = Field(default_factory=list)


class Symbol(BaseModel):
    """Referencia simbólica a un símbolo del registry."""
    model_config = ConfigDict(extra="forbid")

    library: str
    name: str

    @property
    def full_id(self) -> str:
        return f"{self.library}:{self.name}"


class Footprint(BaseModel):
    """Referencia simbólica a un footprint del registry."""
    model_config = ConfigDict(extra="forbid")

    library: str
    name: str

    @property
    def full_id(self) -> str:
        return f"{self.library}:{self.name}"


# ────────────────────────────────────────────────────────────────────────────
# Placement
# ────────────────────────────────────────────────────────────────────────────


class PlacementInfo(BaseModel):
    """Posición/rotación/cara — la asigna el placement engine."""
    model_config = ConfigDict(extra="forbid")

    position: Vec2
    rotation_deg: float = 0.0
    side: Side = Side.TOP

    @field_validator("rotation_deg")
    @classmethod
    def _normalize_rotation(cls, v: float) -> float:
        # KiCad acepta cualquier ángulo; normalizamos a [0, 360).
        v = v % 360.0
        if v < 0:
            v += 360.0
        return v


# ────────────────────────────────────────────────────────────────────────────
# Component
# ────────────────────────────────────────────────────────────────────────────


class Component(BaseModel):
    """Componente del circuito.

    `type` es la clave del component_registry (ej. "esp32_devkit_v1").
    El registry resuelve `type` → footprint + symbol + pinout.
    El IR puede llevar overrides explícitos (`symbol`, `footprint`) que
    pisan al registry; se usa cuando el LLM detecta una variante.
    """
    model_config = ConfigDict(extra="forbid")

    ref: RefId
    type: str = Field(min_length=1)
    value: str | None = None
    symbol: Symbol | None = None
    footprint: Footprint | None = None
    pins: list[Pin] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)
    placement: PlacementInfo | None = None

    @field_validator("pins")
    @classmethod
    def _no_duplicate_pin_numbers(cls, pins: list[Pin]) -> list[Pin]:
        seen: set[str] = set()
        for p in pins:
            if p.number in seen:
                raise ValueError(f"Pin number duplicado: {p.number}")
            seen.add(p.number)
        return pins

    def pin(self, number_or_name: str) -> Pin | None:
        for p in self.pins:
            if p.number == number_or_name or p.name == number_or_name:
                return p
        return None


# ────────────────────────────────────────────────────────────────────────────
# Net
# ────────────────────────────────────────────────────────────────────────────


class Node(BaseModel):
    """Punto de conexión: (component_ref, pin)."""
    model_config = ConfigDict(extra="forbid")

    ref: RefId
    pin: PinId

    def __str__(self) -> str:
        return f"{self.ref}.{self.pin}"


class Net(BaseModel):
    """Net eléctrica."""
    model_config = ConfigDict(extra="forbid")

    name: NetName
    nodes: list[Node] = Field(default_factory=list)
    # Clase de net: "power", "ground", "signal", "high_voltage", "diff_pair".
    # La usa el routing engine para decidir trace_width.
    net_class: str = "signal"

    @model_validator(mode="after")
    def _no_duplicate_nodes(self) -> "Net":
        seen: set[tuple[str, str]] = set()
        for n in self.nodes:
            key = (n.ref, n.pin)
            if key in seen:
                raise ValueError(f"Nodo duplicado en net '{self.name}': {n}")
            seen.add(key)
        return self


# ────────────────────────────────────────────────────────────────────────────
# Routing output
# ────────────────────────────────────────────────────────────────────────────


class Trace(BaseModel):
    """Tramo de cobre generado por el routing engine."""
    model_config = ConfigDict(extra="forbid")

    net: NetName
    points: list[Vec2] = Field(min_length=2)
    width_mm: float = Field(gt=0)
    layer: Layer = Layer.F_CU


class Via(BaseModel):
    """Vía between layers."""
    model_config = ConfigDict(extra="forbid")

    net: NetName
    position: Vec2
    drill_mm: float = Field(gt=0)
    diameter_mm: float = Field(gt=0)
    from_layer: Layer = Layer.F_CU
    to_layer: Layer = Layer.B_CU


# ────────────────────────────────────────────────────────────────────────────
# Board / DesignRules
# ────────────────────────────────────────────────────────────────────────────


class DesignRules(BaseModel):
    """Reglas de diseño (clearances, widths, drill sizes)."""
    model_config = ConfigDict(extra="forbid")

    clearance_mm: float = Field(default=0.2, gt=0)
    trace_width_signal_mm: float = Field(default=0.25, gt=0)
    trace_width_power_mm: float = Field(default=0.5, gt=0)
    trace_width_high_current_mm: float = Field(default=1.0, gt=0)
    via_drill_mm: float = Field(default=0.4, gt=0)
    via_diameter_mm: float = Field(default=0.8, gt=0)
    pad_pad_clearance_mm: float = Field(default=0.2, gt=0)
    grid_mm: float = Field(default=2.54, gt=0)
    margin_mm: float = Field(default=2.0, ge=0)


class Board(BaseModel):
    """Board outline + stackup."""
    model_config = ConfigDict(extra="forbid")

    width_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)
    origin: Vec2 = Field(default_factory=lambda: Vec2(x=0, y=0))
    layers: list[Layer] = Field(default_factory=lambda: [Layer.F_CU, Layer.B_CU])


# ────────────────────────────────────────────────────────────────────────────
# Constraints / Validation
# ────────────────────────────────────────────────────────────────────────────


class Constraint(BaseModel):
    """Restricción declarativa adjunta al circuito.

    Ejemplos:
        kind="placement_zone", target="U1", payload={"zone":"mcu"}
        kind="net_class",      target="VCC", payload={"class":"power"}
        kind="forbid_pin",     target="U1", payload={"pins":["GPIO6"]}
    """
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1)
    target: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ValidationIssue(BaseModel):
    """Output de constraint engine / DRC."""
    model_config = ConfigDict(extra="forbid")

    code: str
    severity: Severity
    message: str
    component: str | None = None
    net: str | None = None
    pin: str | None = None
    rule: str | None = None  # nombre del ConstraintRule que disparó


# ────────────────────────────────────────────────────────────────────────────
# Circuit raíz
# ────────────────────────────────────────────────────────────────────────────


class CircuitMetadata(BaseModel):
    """Metadata del circuito — no afecta semántica eléctrica."""
    model_config = ConfigDict(extra="forbid")

    title: str = ""
    domain: str | None = None  # iot, industrial, audio, power, ...
    mcu: str | None = None     # tipo de MCU principal (registry key)
    power: str | None = None   # "5V USB", "12V DC", "220VAC", ...
    version: str = "1.0"
    description: str = ""


class Circuit(BaseModel):
    """Documento raíz del IR."""
    model_config = ConfigDict(extra="forbid")

    metadata: CircuitMetadata = Field(default_factory=CircuitMetadata)
    components: list[Component] = Field(default_factory=list)
    nets: list[Net] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    design_rules: DesignRules = Field(default_factory=DesignRules)
    board: Board | None = None
    traces: list[Trace] = Field(default_factory=list)
    vias: list[Via] = Field(default_factory=list)

    # ── Validación estructural ──────────────────────────────────────────────

    @model_validator(mode="after")
    def _check_unique_refs(self) -> "Circuit":
        seen: set[str] = set()
        for c in self.components:
            if c.ref in seen:
                raise ValueError(f"Componente con ref duplicada: {c.ref}")
            seen.add(c.ref)
        return self

    @model_validator(mode="after")
    def _check_unique_net_names(self) -> "Circuit":
        seen: set[str] = set()
        for n in self.nets:
            if n.name in seen:
                raise ValueError(f"Net con nombre duplicado: {n.name}")
            seen.add(n.name)
        return self

    @model_validator(mode="after")
    def _check_node_refs_exist(self) -> "Circuit":
        comp_refs = {c.ref for c in self.components}
        for net in self.nets:
            for node in net.nodes:
                if node.ref not in comp_refs:
                    raise ValueError(
                        f"Net '{net.name}' referencia componente inexistente: {node.ref}"
                    )
        return self

    # ── Lookups ────────────────────────────────────────────────────────────

    def component(self, ref: str) -> Component | None:
        for c in self.components:
            if c.ref == ref:
                return c
        return None

    def net(self, name: str) -> Net | None:
        for n in self.nets:
            if n.name == name:
                return n
        return None

    def nets_of(self, ref: str) -> list[Net]:
        return [n for n in self.nets if any(node.ref == ref for node in n.nodes)]

    # ── Serialización ───────────────────────────────────────────────────────

    def to_json(self, *, indent: int | None = 2) -> str:
        return self.model_dump_json(indent=indent, exclude_none=True)

    @classmethod
    def from_json(cls, data: str | bytes) -> "Circuit":
        return cls.model_validate_json(data)
