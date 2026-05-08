"""Loader + schema del Component Registry."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Iterable

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from tools.eda.ir.types import ElectricalType


# ────────────────────────────────────────────────────────────────────────────
# Schema
# ────────────────────────────────────────────────────────────────────────────


class VoltageSpec(BaseModel):
    """Rango de operación + lógica."""
    model_config = ConfigDict(extra="forbid")

    vcc_min: float = Field(gt=0)
    vcc_max: float = Field(gt=0)
    logic: float | None = None  # nivel lógico (3.3 / 5.0). None = passive/sin lógica.

    @field_validator("vcc_max")
    @classmethod
    def _max_ge_min(cls, v: float, info) -> float:
        vmin = info.data.get("vcc_min")
        if vmin is not None and v < vmin:
            raise ValueError(f"vcc_max ({v}) < vcc_min ({vmin})")
        return v


class PinSpec(BaseModel):
    """Definición de un pin en el registry."""
    model_config = ConfigDict(extra="forbid")

    number: str = Field(min_length=1)
    name: str = Field(min_length=1)
    electrical_type: ElectricalType = ElectricalType.UNSPECIFIED
    # Capabilities: ADC, PWM, I2C_SDA, I2C_SCL, SPI_SCK, SPI_MOSI, SPI_MISO,
    # SPI_CS, UART_TX, UART_RX, GPIO, INPUT_ONLY, BOOT_STRAP, FLASH_INTERNAL,
    # POWER, GROUND, SIGNAL, RESET, CLOCK, DATA.
    functions: list[str] = Field(default_factory=list)
    description: str = ""


class BusPins(BaseModel):
    """Pines preferidos para un bus estándar (I2C/SPI/UART)."""
    model_config = ConfigDict(extra="forbid")

    sda: str | None = None
    scl: str | None = None
    sck: str | None = None
    miso: str | None = None
    mosi: str | None = None
    cs: str | None = None
    tx: str | None = None
    rx: str | None = None


class MCUSpec(BaseModel):
    """Sección específica de MCU — capabilities, pines forbidden, buses."""
    model_config = ConfigDict(extra="forbid")

    forbidden_pins: list[str] = Field(default_factory=list)
    input_only_pins: list[str] = Field(default_factory=list)
    boot_strapping_pins: list[str] = Field(default_factory=list)
    adc_pins: list[str] = Field(default_factory=list)
    dac_pins: list[str] = Field(default_factory=list)
    pwm_pins: list[str] = Field(default_factory=list)  # ['*'] = todos
    preferred_buses: dict[str, BusPins] = Field(default_factory=dict)


class WiringRequirement(BaseModel):
    """Requisito de cableado externo (pull-up, bypass cap, flyback, etc.).

    Ejemplos:
        kind=pullup, pin=DATA, target=VCC, value=10k
        kind=bypass_cap, target=VCC, value=100nF
        kind=bulk_cap, target=VCC, value=100uF
        kind=flyback_diode, kind_polarity=cathode_to_control
        kind=level_shifter, pin=ECHO, from=5V, to=3.3V
    """
    model_config = ConfigDict(extra="forbid", coerce_numbers_to_str=True)

    kind: str = Field(min_length=1)
    pin: str | None = None
    target: str | None = None
    value: str | None = None
    reason: str = ""
    severity: str = "warning"  # error | warning | info


class ComponentSpec(BaseModel):
    """Definición completa de un componente."""
    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1)
    category: str = Field(min_length=1)  # mcu | sensor | actuator | passive | ic | display | connector | power
    display_name: str = ""
    aliases: list[str] = Field(default_factory=list)
    voltage: VoltageSpec | None = None
    footprint_library: str
    footprint_name: str
    symbol_library: str
    symbol_name: str
    pins: list[PinSpec] = Field(default_factory=list)
    mcu: MCUSpec | None = None
    wiring_requirements: list[WiringRequirement] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    critical: list[str] = Field(default_factory=list)
    # SMD: si True, el PCB exporter usa pads SMD; si False, THT.
    smd: bool = False

    @field_validator("pins")
    @classmethod
    def _no_dup_pin_numbers(cls, pins: list[PinSpec]) -> list[PinSpec]:
        seen: set[str] = set()
        for p in pins:
            if p.number in seen:
                raise ValueError(f"Pin number duplicado: {p.number}")
            seen.add(p.number)
        return pins

    @property
    def footprint_full_id(self) -> str:
        return f"{self.footprint_library}:{self.footprint_name}"

    @property
    def symbol_full_id(self) -> str:
        return f"{self.symbol_library}:{self.symbol_name}"

    def pin(self, number_or_name: str) -> PinSpec | None:
        for p in self.pins:
            if p.number == number_or_name or p.name == number_or_name:
                return p
        return None

    def pins_with_function(self, function: str) -> list[PinSpec]:
        return [p for p in self.pins if function in p.functions]

    def is_pin_valid(self, pin: str) -> bool:
        """Para MCUs: ¿el pin existe (por número o nombre)?"""
        return self.pin(pin) is not None

    def is_pin_forbidden(self, pin: str) -> bool:
        if not self.mcu:
            return False
        return pin in self.mcu.forbidden_pins

    def is_pin_input_only(self, pin: str) -> bool:
        if not self.mcu:
            return False
        return pin in self.mcu.input_only_pins


# ────────────────────────────────────────────────────────────────────────────
# Registry
# ────────────────────────────────────────────────────────────────────────────


class Registry(BaseModel):
    """Colección de ComponentSpec con lookups por type/alias."""
    model_config = ConfigDict(extra="forbid")

    components: dict[str, ComponentSpec] = Field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.components)

    def __iter__(self) -> Iterable[ComponentSpec]:  # type: ignore[override]
        return iter(self.components.values())

    def get(self, type_or_alias: str) -> ComponentSpec | None:
        if not type_or_alias:
            return None
        key = type_or_alias.lower().strip()
        # 1. lookup directo por type
        if key in self.components:
            return self.components[key]
        # 2. lookup exacto por alias (case-insensitive)
        for spec in self.components.values():
            if key in (a.lower() for a in spec.aliases):
                return spec
        return None

    def require(self, type_or_alias: str) -> ComponentSpec:
        spec = self.get(type_or_alias)
        if spec is None:
            raise KeyError(f"Componente no encontrado en registry: {type_or_alias!r}")
        return spec

    def by_category(self, category: str) -> list[ComponentSpec]:
        return [c for c in self.components.values() if c.category == category]

    def add(self, spec: ComponentSpec) -> None:
        if spec.type in self.components:
            raise ValueError(f"Componente duplicado en registry: {spec.type}")
        self.components[spec.type] = spec

    def find_in_text(self, text: str) -> list[ComponentSpec]:
        """Extrae componentes mencionados en una descripción libre (substring).

        A diferencia de `get()` (lookup exacto), este método barre `type` y
        `aliases` como substrings sobre el texto en minúsculas. Pensado para
        construir el contexto del prompt LLM a partir de la descripción del
        usuario. Devuelve cada match una sola vez, en orden de definición.
        """
        if not text:
            return []
        haystack = text.lower()
        matched: dict[str, ComponentSpec] = {}
        for spec in self.components.values():
            keys = [spec.type, *spec.aliases]
            for k in keys:
                k_l = k.lower().strip()
                if not k_l:
                    continue
                if k_l in haystack:
                    matched[spec.type] = spec
                    break
        return list(matched.values())


# ────────────────────────────────────────────────────────────────────────────
# Carga
# ────────────────────────────────────────────────────────────────────────────


_DATA_DIR = Path(__file__).parent / "data"


def _load_yaml_files(data_dir: Path) -> Registry:
    if not data_dir.exists():
        raise FileNotFoundError(f"Registry data dir no existe: {data_dir}")

    registry = Registry()
    for yaml_path in sorted(data_dir.rglob("*.yaml")):
        with yaml_path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        if raw is None:
            continue
        try:
            spec = ComponentSpec.model_validate(raw)
        except Exception as e:
            raise ValueError(f"Error parseando {yaml_path}: {e}") from e
        registry.add(spec)
    return registry


@lru_cache(maxsize=1)
def get_registry() -> Registry:
    """Singleton cargado on first call."""
    return _load_yaml_files(_DATA_DIR)


def resolve(type_or_alias: str) -> ComponentSpec | None:
    """Atajo: resolver una clave contra el registry default."""
    return get_registry().get(type_or_alias)


# ────────────────────────────────────────────────────────────────────────────
# Prompt formatting
# ────────────────────────────────────────────────────────────────────────────


def _voltage_str(v: VoltageSpec | None) -> str:
    if v is None:
        return ""
    if v.vcc_min == v.vcc_max:
        return f"{v.vcc_min:g}V"
    return f"{v.vcc_min:g}V–{v.vcc_max:g}V"


def _wiring_line(w: WiringRequirement) -> str:
    parts: list[str] = [w.kind]
    if w.pin and w.target:
        parts.append(f"{w.pin}→{w.target}")
    elif w.pin:
        parts.append(f"pin={w.pin}")
    elif w.target:
        parts.append(f"target={w.target}")
    if w.value:
        parts.append(f"= {w.value}")
    head = " ".join(parts)
    suffix = f" [{w.severity}]"
    body = f": {w.reason}" if w.reason else ""
    return f"{head}{suffix}{body}"


def format_pinouts_for_prompt(specs: list[ComponentSpec]) -> str:
    """Formato del bloque inyectado en el prompt LLM antes de la netlist.

    Reemplaza `tools.component_pinouts.get_pinout_context_for_prompt` consumiendo
    el Component Registry como fuente de verdad. Devuelve "" si la lista es vacía.
    """
    if not specs:
        return ""

    lines = ["PINOUTS VERIFICADOS — usá estos datos exactos en la netlist:"]
    for spec in specs:
        label = spec.display_name or spec.type
        voltage = _voltage_str(spec.voltage)
        header = f"\n▶ {label}" + (f" ({voltage})" if voltage else "")
        lines.append(header)
        for pin in spec.pins:
            tags: list[str] = []
            if pin.functions:
                tags.extend(pin.functions)
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            desc = f" — {pin.description}" if pin.description else ""
            lines.append(f"   {pin.name} (pin {pin.number}){tag_str}{desc}")
        for w in spec.wiring_requirements:
            lines.append(f"   → {_wiring_line(w)}")
        for note in spec.notes:
            lines.append(f"   • {note}")
        for warn in spec.critical:
            lines.append(f"   ⚠ CRÍTICO: {warn}")

    return "\n".join(lines)
