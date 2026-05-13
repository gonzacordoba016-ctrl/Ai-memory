import pytest
from tools.circuit_synthesizer import CircuitSynthesizer

def test_mq2_synthesizes():
    cs = CircuitSynthesizer()
    r = cs.synthesize({"mcu": "ESP32", 
                       "blocks": [{"type": "mq2"}]})
    types = [c["type"] for c in r["components"]]
    assert "mq2" in types

def test_ne555_synthesizes():
    cs = CircuitSynthesizer()
    r = cs.synthesize({"mcu": "ESP32",
                       "blocks": [{"type": "ne555"}]})
    types = [c["type"] for c in r["components"]]
    assert "ne555" in types

def test_neopixel_synthesizes():
    cs = CircuitSynthesizer()
    r = cs.synthesize({"mcu": "ESP32",
                       "blocks": [{"type": "neopixel"}]})
    types = [c["type"] for c in r["components"]]
    assert "neopixel" in types

def test_lcd_i2c_synthesizes():
    cs = CircuitSynthesizer()
    r = cs.synthesize({"mcu": "ESP32",
                       "blocks": [{"type": "lcd_i2c"}]})
    types = [c["type"] for c in r["components"]]
    assert "lcd_i2c" in types

def test_unknown_type_uses_generic_if_in_library():
    cs = CircuitSynthesizer()
    r = cs.synthesize({"mcu": "ESP32",
                       "blocks": [{"type": "hx711"}]})
    types = [c["type"] for c in r["components"]]
    assert "hx711" in types

def test_truly_unknown_type_is_skipped():
    cs = CircuitSynthesizer()
    r = cs.synthesize({"mcu": "ESP32",
                       "blocks": [{"type": "xyz_inexistente"}]})
    # No debe crashear, solo ignorar
    assert len(r["components"]) >= 1  # al menos el MCU
