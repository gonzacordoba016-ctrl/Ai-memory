"""Passive component definitions."""
from __future__ import annotations

from tools.eda.library.base import ComponentDef, FootprintDef, Symbol3DDef, make_pins


RESISTOR = ComponentDef(
    type="resistor",
    name="Resistor",
    category="passive",
    aliases=["resistor", "resistencia", "res"],
    pins=make_pins(["1", "2"], left_count=1),
    footprint=FootprintDef(width_mm=6.5, height_mm=2.5, package="AXIAL"),
    symbol_3d=Symbol3DDef(geometry="cylinder", width_mm=6.5, height_mm=2.0, depth_mm=2.0, color_hex="#d4b896", details={"bands": True}),
    voltage_min=0.0,
    voltage_max=250.0,
    current_ma=0.0,
)

CAPACITOR = ComponentDef(
    type="capacitor",
    name="Ceramic Capacitor",
    category="passive",
    aliases=["capacitor", "cap", "capacitor_ceramic"],
    pins=make_pins(["1", "2"], left_count=1),
    footprint=FootprintDef(width_mm=3.0, height_mm=3.0, package="RADIAL"),
    symbol_3d=Symbol3DDef(geometry="cylinder", width_mm=3.0, height_mm=4.0, depth_mm=3.0, color_hex="#d8a51d", details={"polarized": False}),
    voltage_min=0.0,
    voltage_max=50.0,
    current_ma=0.0,
)

CAPACITOR_ELECTROLYTIC = ComponentDef(
    type="capacitor_electrolytic",
    name="Electrolytic Capacitor",
    category="passive",
    aliases=["capacitor_electrolytic", "cap_electrolytic", "electrolytic", "capacitor_polarized"],
    pins=make_pins(["+", "-"], left_count=1, power={"+"}, ground={"-"}),
    footprint=FootprintDef(width_mm=8.0, height_mm=8.0, package="RADIAL"),
    symbol_3d=Symbol3DDef(geometry="cylinder", width_mm=8.0, height_mm=12.0, depth_mm=8.0, color_hex="#1a3a8f", details={"polarized": True, "stripe": True}),
    voltage_min=0.0,
    voltage_max=50.0,
    current_ma=0.0,
)

LED = ComponentDef(
    type="led",
    name="LED",
    category="passive",
    aliases=["led", "diodo_led", "led_red", "led_green", "led_blue", "led_yellow", "led_white"],
    pins=make_pins(["A", "K"], left_count=1, power={"A"}, ground={"K"}),
    footprint=FootprintDef(width_mm=5.0, height_mm=5.0, package="RADIAL"),
    symbol_3d=Symbol3DDef(geometry="cylinder", width_mm=5.0, height_mm=8.0, depth_mm=5.0, color_hex="#ff3333", details={"lens": True}),
    voltage_min=1.8,
    voltage_max=3.3,
    current_ma=20.0,
    criticals=["Requiere resistencia serie para limitar corriente."],
)

DIODE = ComponentDef(
    type="diode",
    name="Diode",
    category="passive",
    aliases=["diode", "1n4007", "1n4148", "1n5819", "schottky_diode", "flyback_diode"],
    pins=make_pins(["A", "K"], left_count=1, power={"A"}, ground={"K"}),
    footprint=FootprintDef(width_mm=6.5, height_mm=2.5, package="AXIAL"),
    symbol_3d=Symbol3DDef(geometry="cylinder", width_mm=6.5, height_mm=2.4, depth_mm=2.4, color_hex="#888888", details={"cathode_band": True}),
    voltage_min=0.0,
    voltage_max=1000.0,
    current_ma=1000.0,
)
