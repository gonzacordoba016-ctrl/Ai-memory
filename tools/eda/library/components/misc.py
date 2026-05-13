"""Miscellaneous component definitions."""
from __future__ import annotations

from tools.eda.library.base import ComponentDef, FootprintDef, Symbol3DDef, make_pins


CONNECTOR = ComponentDef(
    type="connector",
    name="Screw Terminal / Header Connector",
    category="connector",
    aliases=["connector", "terminal_block", "screw_terminal", "bornera", "header"],
    pins=make_pins(["1", "2"], left_count=1),
    footprint=FootprintDef(width_mm=10.0, height_mm=8.0, package="TERMINAL_BLOCK", is_module=True),
    symbol_3d=Symbol3DDef(geometry="box", width_mm=10.0, height_mm=8.0, depth_mm=8.0, color_hex="#2374c6", details={"screw_terminals": 2}),
    voltage_min=0.0,
    voltage_max=250.0,
    current_ma=10000.0,
)

FUSE = ComponentDef(
    type="fuse",
    name="Fuse Holder",
    category="protection",
    aliases=["fuse", "fusible", "polyfuse", "resettable_fuse"],
    pins=make_pins(["1", "2"], left_count=1),
    footprint=FootprintDef(width_mm=30.0, height_mm=14.0, package="FUSE_5X20"),
    symbol_3d=Symbol3DDef(geometry="cylinder", width_mm=30.0, height_mm=6.0, depth_mm=6.0, color_hex="#eeeeee", details={"holder": True}),
    voltage_min=0.0,
    voltage_max=250.0,
    current_ma=5000.0,
)

NE555 = ComponentDef(
    type="ne555",
    name="NE555 Timer",
    category="ic",
    aliases=["ne555", "ne 555", "555", "timer 555", "temporizador", "oscilador 555"],
    pins=make_pins(["GND", "TRIG", "OUT", "RESET", "CTRL", "THR", "DISCH", "VCC"], left_count=4, power={"VCC", "RESET"}),
    footprint=FootprintDef(width_mm=9.8, height_mm=6.4, package="DIP8"),
    symbol_3d=Symbol3DDef(geometry="dip", width_mm=9.8, height_mm=4.0, depth_mm=6.4, color_hex="#111111", details={"pins": 8, "notch": True}),
    voltage_min=4.5,
    voltage_max=16.0,
    current_ma=15.0,
)

NEOPIXEL = ComponentDef(
    type="neopixel",
    name="WS2812B NeoPixel LED",
    category="display",
    aliases=["neopixel", "ws2812", "ws2812b", "led rgb", "led direccionable", "rgb strip"],
    pins=make_pins(["VDD", "DOUT", "GND", "DIN"], left_count=2, power={"VDD"}),
    footprint=FootprintDef(width_mm=5.0, height_mm=5.0, package="PLCC4", pad_pitch_mm=2.54),
    symbol_3d=Symbol3DDef(geometry="box", width_mm=5.0, height_mm=1.6, depth_mm=5.0, color_hex="#f2f2f2", details={"rgb_lens": True, "addressable": True}),
    voltage_min=3.7,
    voltage_max=5.3,
    current_ma=60.0,
    criticals=["Usar resistencia serie de 300-500 ohm en DIN y capacitor bulk en tiras largas."],
)
