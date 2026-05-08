"""Tests del Component Registry — carga YAML, lookups, schema."""
from __future__ import annotations

import pytest

from tools.eda.component_registry import (
    ComponentSpec,
    PinSpec,
    WiringRequirement,
    format_pinouts_for_prompt,
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


# ── format_pinouts_for_prompt ──────────────────────────────────────────────


def test_format_pinouts_empty_returns_empty_string():
    assert format_pinouts_for_prompt([]) == ""


def test_format_pinouts_renders_known_component():
    reg = get_registry()
    spec = reg.require("dht22")
    out = format_pinouts_for_prompt([spec])
    assert out.startswith("PINOUTS VERIFICADOS")
    assert "DHT22" in out
    assert "DATA" in out and "VCC" in out
    assert "pullup" in out
    assert "10k" in out
    assert "CRÍTICO" in out


def test_format_pinouts_multiple_components():
    reg = get_registry()
    specs = [reg.require("dht22"), reg.require("hc_sr04")]
    out = format_pinouts_for_prompt(specs)
    assert "DHT22" in out
    assert "HC-SR04" in out or "hc_sr04" in out.lower()
    assert out.count("▶") == 2


# ── Registry.find_in_text (substring extraction) ──────────────────────────


def test_find_in_text_empty():
    reg = get_registry()
    assert reg.find_in_text("") == []


def test_find_in_text_single_match():
    reg = get_registry()
    found = reg.find_in_text("Quiero un sensor DHT22 conectado al ESP32")
    types = {s.type for s in found}
    assert "dht22" in types
    assert "esp32" in types


def test_find_in_text_returns_each_component_once():
    reg = get_registry()
    found = reg.find_in_text("dht22 dht22 dht22")
    types = [s.type for s in found]
    assert types.count("dht22") == 1


def test_find_in_text_no_match():
    reg = get_registry()
    assert reg.find_in_text("xyzzy plugh nonsense") == []


# ── WiringRequirement value coercion ──────────────────────────────────────


def test_wiring_requirement_value_accepts_int():
    """value=470 (int) debe coercionarse a "470" sin lanzar."""
    w = WiringRequirement(kind="bulk_cap", target="VCC", value=470)
    assert w.value == "470"


def test_wiring_requirement_value_accepts_float():
    w = WiringRequirement(kind="pullup", pin="DATA", target="VCC", value=4.7)
    assert w.value == "4.7"


def test_wiring_requirement_value_accepts_str():
    w = WiringRequirement(kind="pullup", pin="DATA", target="VCC", value="10k")
    assert w.value == "10k"


# ── MQ gas sensors ──────────────────────────────────────────────────────────


def test_registry_has_mq_sensors():
    reg = get_registry()
    for t in ("mq2", "mq7", "mq135"):
        spec = reg.get(t)
        assert spec is not None, f"MQ sensor faltante: {t}"
        assert spec.category == "sensor"
        assert any("explosivas" in c.lower() for c in spec.critical), \
            f"{t} sin warning de atmósferas explosivas"
        assert any("calentamiento" in c.lower() or "pre-calentamiento" in c.lower()
                   for c in spec.critical), f"{t} sin warning de pre-calentamiento"


def test_find_in_text_resolves_sensor_gas():
    reg = get_registry()
    assert reg.find_in_text("sensor gas") != []
