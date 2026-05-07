"""
Component Registry — fuente única de verdad de componentes.

Cada componente se define en un archivo YAML bajo `data/`. El loader valida
el schema con pydantic y expone una API de consulta determinista.

Reemplaza progresivamente:
    - tools/component_pinouts.py  (PINOUTS dict)
    - tools/mcu_pinout_validator.py  (MCU_VALID_PINS)
    - tools/kicad_exporter.py:_TYPE_TO_FOOTPRINT
    - tools/kicad_pcb_exporter.py:_SMD_TYPES
    - aliases/keywords dispersos

El Pin Allocator y el Constraint Engine consumen exclusivamente este registry.
"""

from .loader import (
    BusPins,
    ComponentSpec,
    MCUSpec,
    PinSpec,
    Registry,
    VoltageSpec,
    WiringRequirement,
    get_registry,
    resolve,
)

__all__ = [
    "BusPins",
    "ComponentSpec",
    "MCUSpec",
    "PinSpec",
    "Registry",
    "VoltageSpec",
    "WiringRequirement",
    "get_registry",
    "resolve",
]
