"""Global registry for unified component definitions."""
from __future__ import annotations

from tools.eda.library.base import ComponentDef
from tools.eda.library.components import (
    actuators,
    communication,
    displays,
    mcu,
    misc,
    passives,
    power,
    sensors,
)


_REGISTRY: dict[str, ComponentDef] = {}


def _key(type_str: str) -> str:
    return type_str.lower().strip().replace(" ", "_")


def _register(*components: ComponentDef) -> None:
    for component in components:
        _REGISTRY[_key(component.type)] = component
        for alias in component.aliases:
            _REGISTRY[_key(alias)] = component


_register(
    mcu.ESP32,
    mcu.ESP8266,
    mcu.ARDUINO_UNO,
    mcu.ARDUINO_NANO,
    mcu.ARDUINO_MEGA,
    mcu.STM32,
    mcu.PICO,
    sensors.BMP280,
    sensors.DHT11,
    sensors.DHT22,
    sensors.DS18B20,
    sensors.DS3231,
    sensors.FC28,
    sensors.HC_SR04,
    sensors.HX711,
    sensors.INA219,
    sensors.MPU6050,
    sensors.MQ2,
    sensors.MQ7,
    sensors.MQ135,
    sensors.PIR,
    displays.OLED_SSD1306,
    displays.LCD_I2C,
    actuators.RELAY_MODULE,
    actuators.SERVO,
    actuators.L298N,
    actuators.A4988,
    actuators.DRV8825,
    passives.RESISTOR,
    passives.CAPACITOR,
    passives.CAPACITOR_ELECTROLYTIC,
    passives.LED,
    passives.DIODE,
    power.LM7805,
    power.LM317,
    power.AMS1117,
    communication.NRF24L01,
    communication.HC05,
    misc.CONNECTOR,
    misc.FUSE,
    misc.NE555,
    misc.NEOPIXEL,
)


def get_component(type_str: str) -> ComponentDef | None:
    if not type_str:
        return None
    return _REGISTRY.get(_key(type_str))


def list_types() -> list[str]:
    return sorted({component.type for component in _REGISTRY.values()})
