"""Tests for the unified EDA component library."""
from __future__ import annotations

from tools.eda.library import get_component, list_types


REQUIRED_TYPES = [
    "a4988",
    "ams1117",
    "arduino_mega",
    "arduino_nano",
    "arduino_uno",
    "bmp280",
    "capacitor",
    "capacitor_electrolytic",
    "connector",
    "dht11",
    "dht22",
    "diode",
    "drv8825",
    "ds18b20",
    "ds3231",
    "esp32",
    "esp8266",
    "fc28",
    "fuse",
    "hc05",
    "hc_sr04",
    "hx711",
    "ina219",
    "l298n",
    "lcd_i2c",
    "led",
    "lm317",
    "lm7805",
    "mpu6050",
    "mq135",
    "mq2",
    "mq7",
    "ne555",
    "neopixel",
    "nrf24l01",
    "oled_ssd1306",
    "pir",
    "raspberry_pi_pico",
    "relay_module",
    "resistor",
    "servo",
    "stm32",
]


def test_get_esp32():
    c = get_component("esp32")
    assert c is not None
    assert c.type == "esp32"
    assert c.footprint.width_mm == 25.5
    assert any(p.name == "GND" for p in c.pins)


def test_alias_resolution():
    assert get_component("esp-32").type == "esp32"
    assert get_component("nodemcu").type == "esp8266"
    assert get_component("humedad suelo").type == "fc28"


def test_all_42_types_registered():
    types = list_types()
    assert len(types) == 42
    for type_name in REQUIRED_TYPES:
        assert type_name in types, f"{type_name} no esta en la libreria"


def test_all_have_footprint():
    for type_name in list_types():
        c = get_component(type_name)
        assert c is not None
        assert c.footprint.width_mm > 0
        assert c.footprint.height_mm > 0
        assert c.footprint.package != ""


def test_all_have_3d():
    for type_name in list_types():
        c = get_component(type_name)
        assert c is not None
        assert c.symbol_3d.geometry != ""
        assert c.symbol_3d.width_mm > 0
        assert c.symbol_3d.height_mm > 0
        assert c.symbol_3d.depth_mm > 0
