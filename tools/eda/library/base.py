"""Unified component library schema.

This module is intentionally independent from the existing YAML registry and
renderers. The next integration step can consume these dataclasses as the single
source of truth for symbols, PCB footprints, and 3D models.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PinDef:
    name: str
    number: int
    side: str
    type: str


@dataclass
class FootprintDef:
    width_mm: float
    height_mm: float
    package: str
    pad_pitch_mm: float = 2.54
    is_module: bool = False


@dataclass
class Symbol3DDef:
    geometry: str
    width_mm: float
    height_mm: float
    depth_mm: float
    color_hex: str
    details: dict = field(default_factory=dict)


@dataclass
class ComponentDef:
    type: str
    name: str
    category: str
    aliases: list[str]
    pins: list[PinDef]
    footprint: FootprintDef
    symbol_3d: Symbol3DDef
    voltage_min: float = 3.3
    voltage_max: float = 5.0
    current_ma: float = 0.0
    criticals: list[str] = field(default_factory=list)
    notes: str = ""


def make_pins(
    names: list[str],
    *,
    left_count: int | None = None,
    power: set[str] | None = None,
    ground: set[str] | None = None,
    io: set[str] | None = None,
) -> list[PinDef]:
    """Create positioned symbol pins from ordered pin names."""
    power = {p.upper() for p in (power or set())}
    ground = {g.upper() for g in (ground or {"GND"})}
    io = {i.upper() for i in (io or set())}
    left_count = left_count if left_count is not None else (len(names) + 1) // 2

    pins: list[PinDef] = []
    for index, name in enumerate(names, start=1):
        side = "left" if index <= left_count else "right"
        key = name.upper()
        if key in ground or key.startswith("GND"):
            pin_type = "gnd"
        elif key in power or key in {"VCC", "VIN", "VDD", "3V3", "5V", "+", "VMOT", "VS"}:
            pin_type = "power"
        elif (
            key in io
            or key.startswith(("GPIO", "GP", "PA", "PB", "PC", "PD", "D", "A"))
            or key in {"SDA", "SCL", "SCK", "MOSI", "MISO", "CS", "TX", "RX", "DATA", "ECHO", "TRIG"}
        ):
            pin_type = "io"
        else:
            pin_type = "signal"
        pins.append(PinDef(name=name, number=index, side=side, type=pin_type))
    return pins
