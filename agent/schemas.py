"""Modelos Pydantic para outputs LLM de los agentes.

Cada modelo cubre un callsite que históricamente parseaba con
`json.loads(strip(content))`. Reemplazar por `Model.model_validate_json`
da validación de shape y mensajes de error mejores.

Política: `extra="allow"` en todos los modelos para no romper si el LLM
devuelve campos adicionales no documentados (defensive parsing).
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CircuitSpec(BaseModel):
    """Output del template extractor (`_extract_circuit_spec`)."""
    model_config = ConfigDict(extra="allow")

    mcu: str = ""
    blocks: list[dict] = Field(default_factory=list)
    power: str = "3.3V USB"
    domain: str = "synthesized"


class LLMCircuitOutput(BaseModel):
    """Output del LLM full circuit generator y del review pass."""
    model_config = ConfigDict(extra="allow")

    name: str = ""
    description: str = ""
    components: list[dict] = Field(default_factory=list)
    nets: list[dict] = Field(default_factory=list)


class ElectricalCalcResult(BaseModel):
    """Output del electrical calc agent (extracción de parámetros)."""
    model_config = ConfigDict(extra="allow")

    formula: str
    result: float
    unit: str
    steps: list[str] = Field(default_factory=list)


class HardwareDebugResult(BaseModel):
    """Output del hardware design debug LLM."""
    model_config = ConfigDict(extra="allow")

    diagnosis: str = "No pude diagnosticar"
    fixed_code: str = ""


class VisionCircuit(BaseModel):
    """Output del vision agent (análisis de imagen → circuito)."""
    model_config = ConfigDict(extra="allow")

    components: list[dict] = Field(default_factory=list)
    connections: list[dict] = Field(default_factory=list)
    project_name: str = "Circuito analizado por visión"
    power: str = "desconocida"
