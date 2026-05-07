"""Tests del Component Registry — carga YAML, lookups, schema."""
from __future__ import annotations

import pytest

from tools.eda.component_registry import (
    ComponentSpec,
    PinSpec,
    get_registry,
    resolve,
)
from tools.eda.ir import ElectricalType


# ── Carga ───────────────────────────────────────────────────────────────────


def test_registry_loads():
    reg = get_registry()
    assert len(reg) > 0


def test_registry_has_core_mcus():
    reg = get_registry()
    for mcu_type in ("esp32", "arduino_uno", "arduino_nano",
                     "arduino_mega", "esp8266", "raspberry_pi_pico"):
        spec = reg.get(mcu_type)
        assert spec is not None, f"MCU faltante en registry: {mcu_type}"
        assert spec.category == "mcu"
        assert spec.mcu is not None


def test_registry_has_core_passives():
    reg = get_registry()
    for t in ("resistor", "capacitor", "led", "diode"):
        assert reg.get(t) is not None, f"Pasivo faltante: {t}"


# ── Aliases ────────────────────────────────────────────────────────────────


def test_aliases_resolve():
    reg = get_registry()
    # 'arduino' es alias de arduino_uno
    s = reg.get("arduino")
    assert s is not None and s.type == "arduino_uno"
    # 'pico' → raspberry_pi_pico
    s = reg.get("pico")
    assert s is not None and s.type == "raspberry_pi_pico"
    # 'rele' → relay_module
    s = reg.get("rele")
    assert s is not None and s.type == "relay_module"


def test_resolve_shortcut():
    assert resolve("esp32") is not None
    assert resolve("componente_inexistente_xyz") is None


def test_lookup_case_insensitive():
    assert resolve("ESP32") is not None
    assert resolve("Arduino UNO") is not None


# ── Pin lookups ────────────────────────────────────────────────────────────


def test_esp32_forbidden_pins():
    spec = resolve("esp32")
    assert spec is not None
    assert spec.is_pin_forbidden("GPIO6")
    assert spec.is_pin_forbidden("GPIO11")
    assert not spec.is_pin_forbidden("GPIO21")


def test_esp32_input_only():
    spec = resolve("esp32")
    assert spec is not None
    assert spec.is_pin_input_only("GPIO34")
    assert not spec.is_pin_input_only("GPIO21")


def test_arduino_nano_pins_valid():
    spec = resolve("arduino_nano")
    assert spec is not None
    assert spec.is_pin_valid("D7")
    assert spec.is_pin_valid("A6")
    assert not spec.is_pin_valid("D14")  # no existe en Nano


def test_pin_with_function_lookup():
    spec = resolve("arduino_uno")
    assert spec is not None
    pwm_pins = [p.number for p in spec.pins_with_function("PWM")]
    assert "D3" in pwm_pins
    assert "D5" in pwm_pins
    assert "D2" not in pwm_pins  # D2 no es PWM


def test_preferred_buses():
    spec = resolve("esp32")
    assert spec is not None
    assert spec.mcu is not None
    i2c = spec.mcu.preferred_buses["i2c"]
    assert i2c.sda == "GPIO21"
    assert i2c.scl == "GPIO22"


# ── Wiring requirements ────────────────────────────────────────────────────


def test_dht22_requires_pullup():
    spec = resolve("dht22")
    assert spec is not None
    pullups = [w for w in spec.wiring_requirements if w.kind == "pullup"]
    assert len(pullups) == 1
    assert pullups[0].pin == "DATA"
    assert pullups[0].target == "VCC"


def test_led_requires_series_resistor():
    spec = resolve("led")
    assert spec is not None
    kinds = {w.kind for w in spec.wiring_requirements}
    assert "series_resistor" in kinds


# ── Footprints / símbolos ──────────────────────────────────────────────────


def test_full_footprint_id():
    spec = resolve("resistor")
    assert spec is not None
    assert spec.footprint_full_id == \
        "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal"


def test_smd_flag():
    assert resolve("esp32").smd is True
    assert resolve("resistor").smd is False


# ── by_category ────────────────────────────────────────────────────────────


def test_by_category():
    reg = get_registry()
    mcus = reg.by_category("mcu")
    assert len(mcus) >= 6
    sensors = reg.by_category("sensor")
    assert len(sensors) >= 4


# ── Validación schema ──────────────────────────────────────────────────────


def test_pin_spec_rejects_extra():
    with pytest.raises(Exception):
        PinSpec(number="1", name="a", electrical_type=ElectricalType.PASSIVE,
                weird_field=123)  # type: ignore[call-arg]


def test_component_spec_no_dup_pins():
    with pytest.raises(Exception):
        ComponentSpec(
            type="x",
            category="passive",
            footprint_library="X", footprint_name="Y",
            symbol_library="X", symbol_name="Y",
            pins=[
                PinSpec(number="1", name="a"),
                PinSpec(number="1", name="b"),
            ],
        )
