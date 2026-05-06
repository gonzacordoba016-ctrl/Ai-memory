"""Tests for tools.eda.classifier — preserves 6-zone semantics from schematic_renderer."""

import pytest

from tools.eda.classifier import (
    classify_zone,
    comp_group,
    classify,
    ClassifiedComponent,
)


# ── classify_zone ───────────────────────────────────────────────────────────

def test_relay_by_type():
    assert classify_zone({"id": "U1", "type": "relay"}) == "relay"
    assert classify_zone({"id": "U1", "type": "relay_module"}) == "relay"
    assert classify_zone({"id": "U1", "type": "ssr"}) == "relay"


def test_relay_by_id_prefix():
    assert classify_zone({"id": "RL1", "type": "generic"}) == "relay"
    assert classify_zone({"id": "rl42", "type": "whatever"}) == "relay"


def test_ac_by_type():
    for t in ("transformer", "smps", "bridge_rectifier", "fuse", "varistor",
              "mov", "inductor_cm", "ac_filter", "x_capacitor"):
        assert classify_zone({"id": "X", "type": t}) == "ac", t


def test_ac_connector_by_name():
    cases = [
        {"id": "J1", "type": "connector", "name": "AC 220V"},
        {"id": "J1", "type": "connector", "name": "Mains input"},
        {"id": "J1", "type": "connector", "name": "Entrada 110"},
        {"id": "J1", "type": "connector", "name": "Alimentación"},
    ]
    for c in cases:
        assert classify_zone(c) == "ac", c


def test_connector_without_ac_keywords_goes_output():
    assert classify_zone({"id": "J1", "type": "connector", "name": "Header"}) == "output"


def test_mcu_zone_includes_regulators():
    assert classify_zone({"id": "U1", "type": "esp32"}) == "mcu"
    assert classify_zone({"id": "U1", "type": "arduino_uno"}) == "mcu"
    assert classify_zone({"id": "U1", "type": "lm7805"}) == "mcu"
    assert classify_zone({"id": "U1", "type": "ams1117"}) == "mcu"
    assert classify_zone({"id": "U1", "type": "buck_converter"}) == "mcu"


def test_sensor_zone():
    for t in ("bmp280", "dht22", "mpu6050", "ds18b20", "ultrasonic", "sensor_i2c"):
        assert classify_zone({"id": "X", "type": t}) == "sensor", t


def test_display_classified_as_output():
    # Existing 6-zone semantics: displays go to 'output', NOT a separate zone.
    for t in ("oled", "lcd", "tft", "ssd1306"):
        assert classify_zone({"id": "X", "type": t}) == "output", t


def test_other_fallback():
    assert classify_zone({"id": "R1", "type": "resistor"}) == "other"
    assert classify_zone({"id": "X", "type": "unknown_thing"}) == "other"


def test_resolved_type_takes_precedence():
    comp = {"id": "U1", "type": "generic", "resolved_type": "esp32"}
    assert classify_zone(comp) == "mcu"


def test_relay_id_prefix_beats_type_match():
    # If id starts with 'rl' it's a relay, even if type would suggest something else.
    assert classify_zone({"id": "RL1", "type": "bmp280"}) == "relay"


def test_empty_or_missing_fields():
    assert classify_zone({}) == "other"
    assert classify_zone({"id": None, "type": None, "name": None}) == "other"


# ── comp_group ──────────────────────────────────────────────────────────────

def test_comp_group_buckets():
    assert comp_group({"type": "esp32"}) == "mcu"
    assert comp_group({"type": "capacitor"}) == "power"
    assert comp_group({"type": "button"}) == "input"
    assert comp_group({"type": "led"}) == "output"
    assert comp_group({"type": "wifi_module"}) == "comm"
    assert comp_group({"type": "resistor"}) == "misc"


def test_comp_group_resolved_type_precedence():
    assert comp_group({"type": "generic", "resolved_type": "esp32"}) == "mcu"


# ── classify (list) ─────────────────────────────────────────────────────────

def test_classify_returns_classified_components():
    comps = [
        {"id": "U1", "type": "esp32", "name": "MCU"},
        {"id": "U2", "type": "bmp280", "name": "Sensor"},
        {"id": "RL1", "type": "relay", "name": "Relay"},
    ]
    out = classify(comps)
    assert len(out) == 3
    assert all(isinstance(c, ClassifiedComponent) for c in out)
    assert out[0].zone == "mcu"
    assert out[1].zone == "sensor"
    assert out[2].zone == "relay"


def test_classify_carries_name_and_value():
    comps = [{"id": "R1", "type": "resistor", "name": "Pull-up", "value": "10k"}]
    out = classify(comps)
    assert out[0].name == "Pull-up"
    assert out[0].value == "10k"
    assert out[0].zone == "other"
