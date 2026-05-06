"""Component zone classifier — single source of truth for zone assignment.

Preserves the exact 6-zone semantics of schematic_renderer._classify_zone:
zones are 'ac', 'mcu', 'sensor', 'relay', 'output', 'other'.

Signal flow: AC -> MCU/Power -> Sensors -> Relay -> Output.
"""

from dataclasses import dataclass
from typing import Dict, List

from tools.component_types import (
    _MCU_TYPES,
    _RELAY_TYPES,
    _ZONE_SENSOR_TYPES,
    _ZONE_DISPLAY_TYPES,
)


_POWER_TYPES = {"capacitor", "regulator", "ldo", "dc_dc", "battery", "fuse", "diode",
                "1n4007", "1n5819", "zener"}
_INPUT_TYPES = {"button", "sensor", "moisture_sensor", "temperature_sensor",
                "dht22", "dht11", "bmp280", "ultrasonic", "pir", "encoder",
                "potentiometer", "photoresistor", "microphone"}
_OUTPUT_TYPES = {"led", "led_rgb", "relay", "relay_module", "motor", "servo",
                 "buzzer", "display", "oled", "lcd", "neopixel", "motor_driver"}
_COMM_TYPES = {"wifi_module", "bluetooth", "lora", "zigbee", "can_transceiver",
               "rs485", "ethernet"}

_ZONE_AC_TYPES = {
    "transformer", "smps", "bridge_rectifier", "fuse", "fuse_holder",
    "varistor", "mov", "inductor_cm", "ac_filter", "x_capacitor",
}
_ZONE_MCU_TYPES = _MCU_TYPES | {
    "voltage_regulator", "lm7805", "ams1117", "lm317", "regulator",
    "buck_converter", "boost_converter", "buck_boost", "ldo", "dc_dc",
}


@dataclass
class ClassifiedComponent:
    id: str
    type: str
    zone: str
    name: str
    value: str = ""


def classify_zone(comp: Dict) -> str:
    """Return zone for a single component.

    Returns one of: 'ac', 'mcu', 'sensor', 'relay', 'output', 'other'.
    """
    cid = (comp.get("id", "") or "").lower()
    t = (comp.get("resolved_type") or comp.get("type") or "").lower()
    name = (comp.get("name", "") or "").lower()

    if t in _RELAY_TYPES or cid.startswith("rl"):
        return "relay"

    if t in _ZONE_AC_TYPES:
        return "ac"
    if t == "connector" and (
        "220" in name or "110" in name
        or "ac" in name or "mains" in name
        or "input" in name or "alimenta" in name or "entrada" in name
    ):
        return "ac"

    if t in _ZONE_MCU_TYPES:
        return "mcu"

    if t in _ZONE_SENSOR_TYPES:
        return "sensor"

    if t == "connector":
        return "output"

    if t in _ZONE_DISPLAY_TYPES:
        return "output"

    return "other"


def comp_group(comp: Dict) -> str:
    """Functional group hint for visual styling (NOT zone placement).

    Returns one of: 'mcu', 'power', 'input', 'output', 'comm', 'misc'.
    """
    t = comp.get("resolved_type", comp.get("type", "generic")).lower()
    if t in _MCU_TYPES:    return "mcu"
    if t in _POWER_TYPES:  return "power"
    if t in _INPUT_TYPES:  return "input"
    if t in _OUTPUT_TYPES: return "output"
    if t in _COMM_TYPES:   return "comm"
    return "misc"


def classify(components: List[Dict]) -> List[ClassifiedComponent]:
    """Classify a list of components into ClassifiedComponent records."""
    return [
        ClassifiedComponent(
            id=c.get("id", ""),
            type=(c.get("resolved_type") or c.get("type") or "").lower(),
            zone=classify_zone(c),
            name=c.get("name", ""),
            value=c.get("value", ""),
        )
        for c in components
    ]
