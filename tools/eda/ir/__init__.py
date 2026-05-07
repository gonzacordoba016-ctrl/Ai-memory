"""
Circuit IR — Intermediate Representation tipada del pipeline EDA.

Una vez que el LLM genera la estructura lógica del circuito, el resto del
pipeline (constraint engine, pin allocator, placement, routing, renderer,
exporters) consume *exclusivamente* este IR. Ningún módulo aguas abajo
puede aceptar dicts arbitrarios.

Modelos:
    - Circuit       — el documento raíz
    - Component     — bloque físico (referencia, símbolo, footprint, pines)
    - Pin           — pin individual con tipo eléctrico
    - Net           — net eléctrica con sus nodos
    - Node          — referencia (component, pin)
    - PlacementInfo — coordenadas + rotación + side (asignado por placement engine)
    - Trace         — track/wire generado por routing engine
    - Footprint     — referencia simbólica al footprint en el registry
    - Symbol        — referencia simbólica al símbolo en el registry
    - Board         — board outline + layer stack
    - DesignRules   — clearances, pad sizes, trace widths
    - Constraint    — restricción declarativa
    - ValidationIssue / Severity — issues del constraint engine
    - CircuitMetadata — title, mcu, power, domain, version, etc.
    - Vec2          — coordenada 2D inmutable
"""

from .types import (
    ElectricalType,
    Side,
    Severity,
    Layer,
    Vec2,
)
from .models import (
    Pin,
    Footprint,
    Symbol,
    PlacementInfo,
    Component,
    Node,
    Net,
    Trace,
    Via,
    Board,
    DesignRules,
    Constraint,
    ValidationIssue,
    CircuitMetadata,
    Circuit,
)

__all__ = [
    "ElectricalType",
    "Side",
    "Severity",
    "Layer",
    "Vec2",
    "Pin",
    "Footprint",
    "Symbol",
    "PlacementInfo",
    "Component",
    "Node",
    "Net",
    "Trace",
    "Via",
    "Board",
    "DesignRules",
    "Constraint",
    "ValidationIssue",
    "CircuitMetadata",
    "Circuit",
]
