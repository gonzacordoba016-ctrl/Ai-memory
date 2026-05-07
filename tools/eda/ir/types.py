"""Tipos base del Circuit IR — enums + Vec2."""
from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class ElectricalType(str, Enum):
    """Clasificación eléctrica de un pin (estilo KiCad)."""
    INPUT = "input"
    OUTPUT = "output"
    BIDIRECTIONAL = "bidirectional"
    TRISTATE = "tristate"
    PASSIVE = "passive"
    POWER_IN = "power_in"
    POWER_OUT = "power_out"
    OPEN_COLLECTOR = "open_collector"
    OPEN_EMITTER = "open_emitter"
    NC = "nc"
    UNSPECIFIED = "unspecified"


class Side(str, Enum):
    """Cara del board en la que vive un footprint."""
    TOP = "top"
    BOTTOM = "bottom"


class Layer(str, Enum):
    """Capas KiCad estándar usadas por el pipeline."""
    F_CU = "F.Cu"
    B_CU = "B.Cu"
    F_SILK = "F.SilkS"
    B_SILK = "B.SilkS"
    F_MASK = "F.Mask"
    B_MASK = "B.Mask"
    EDGE_CUTS = "Edge.Cuts"


class Severity(str, Enum):
    """Severidad de un ValidationIssue."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Vec2(BaseModel):
    """Coordenada 2D en milímetros. Inmutable."""
    model_config = ConfigDict(frozen=True)

    x: float
    y: float

    def __add__(self, other: "Vec2") -> "Vec2":
        return Vec2(x=self.x + other.x, y=self.y + other.y)

    def __sub__(self, other: "Vec2") -> "Vec2":
        return Vec2(x=self.x - other.x, y=self.y - other.y)


# Identificadores: strings no vacíos, sin espacios.
RefId = Annotated[
    str,
    Field(min_length=1, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$"),
]
PinId = Annotated[str, Field(min_length=1)]
NetName = Annotated[str, Field(min_length=1)]
