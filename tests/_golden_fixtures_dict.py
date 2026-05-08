"""Fixtures dict gemelos a `_golden_fixtures.py` (Circuit IR).

Cada función retorna un dict con la forma que produce CircuitSynthesizer
(`tools/circuit_synthesizer.py:159-173`). Sirven como input para
`tools.electrical_drc.run_drc(dict)` y para el adaptador `dict_to_ir`.

Diferencia esperada vs IR golden: el dict del synthesizer no tiene campo
`net_class`. `dict_to_ir` lo infiere desde el nombre — los nets MOTOR_*
del fixture motor_l298n_arduino quedarán en `signal`, mientras el IR
golden los tiene marcados como `high_current`.
"""
from __future__ import annotations


def blink_led_esp32() -> dict:
    return {
        "name": "blink_led_esp32",
        "description": "ESP32 con LED+resistencia en GPIO2",
        "_mcu": "esp32",
        "_vcc": 3.3,
        "_synthesized": True,
        "power": "5V USB",
        "warnings": [],
        "components": [
            {"id": "U1", "type": "esp32"},
            {"id": "R1", "type": "resistor", "value": "220"},
            {"id": "LED1", "type": "led"},
        ],
        "nets": [
            {"name": "VCC", "nodes": ["U1.VCC"]},
            {"name": "GND", "nodes": ["U1.GND", "LED1.cathode"]},
            {"name": "LED_DRIVE", "nodes": ["U1.GPIO2", "R1.1"]},
            {"name": "LED_ANODE", "nodes": ["R1.2", "LED1.anode"]},
        ],
    }


def i2c_oled_dht22_esp32() -> dict:
    return {
        "name": "i2c_oled_dht22_esp32",
        "description": "ESP32 lee DHT22 y muestra en OLED I2C",
        "_mcu": "esp32",
        "_vcc": 3.3,
        "_synthesized": True,
        "power": "5V USB",
        "warnings": [],
        "components": [
            {"id": "U1", "type": "esp32"},
            {"id": "DISP", "type": "oled_ssd1306"},
            {"id": "S1", "type": "dht22"},
            {"id": "R1", "type": "resistor", "value": "4.7k"},
            {"id": "R2", "type": "resistor", "value": "4.7k"},
            {"id": "R3", "type": "resistor", "value": "10k"},
            {"id": "C1", "type": "capacitor_electrolytic", "value": "100uF"},
            {"id": "C2", "type": "capacitor", "value": "100nF"},
        ],
        "nets": [
            {"name": "VCC", "nodes": [
                "U1.VCC", "DISP.VCC", "S1.VCC",
                "R1.2", "R2.2", "R3.2",
                "C1.+", "C2.1",
            ]},
            {"name": "GND", "nodes": [
                "U1.GND", "DISP.GND", "S1.GND",
                "C1.-", "C2.2",
            ]},
            {"name": "SDA", "nodes": ["U1.GPIO21", "DISP.SDA", "R1.1"]},
            {"name": "SCL", "nodes": ["U1.GPIO22", "DISP.SCL", "R2.1"]},
            {"name": "DHT_DATA", "nodes": ["U1.GPIO16", "S1.DATA", "R3.1"]},
        ],
    }


def motor_l298n_arduino() -> dict:
    return {
        "name": "motor_l298n_arduino",
        "description": "Arduino Uno controla 1 motor vía L298N",
        "_mcu": "arduino_uno",
        "_vcc": 5.0,
        "_synthesized": True,
        "power": "5V USB",
        "warnings": [],
        "components": [
            {"id": "U1", "type": "arduino_uno"},
            {"id": "DRV", "type": "l298n"},
            {"id": "M1", "type": "motor"},
        ],
        "nets": [
            {"name": "VCC", "nodes": ["U1.VCC", "DRV.VCC"]},
            {"name": "GND", "nodes": ["U1.GND", "DRV.GND"]},
            {"name": "MOTOR_IN1", "nodes": ["U1.D5", "DRV.IN1"]},
            {"name": "MOTOR_IN2", "nodes": ["U1.D6", "DRV.IN2"]},
            {"name": "MOTOR_OUT", "nodes": ["DRV.OUT1", "M1.1"]},
            {"name": "MOTOR_RET", "nodes": ["DRV.OUT2", "M1.2"]},
        ],
    }


ALL_FIXTURES_DICT = {
    "blink_led_esp32": blink_led_esp32,
    "i2c_oled_dht22_esp32": i2c_oled_dht22_esp32,
    "motor_l298n_arduino": motor_l298n_arduino,
}
