"""Power and regulator component definitions."""
from __future__ import annotations

from tools.eda.library.base import ComponentDef, FootprintDef, Symbol3DDef, make_pins


LM7805 = ComponentDef(
    type="lm7805",
    name="LM7805 5V Linear Regulator",
    category="power",
    aliases=["lm7805", "7805", "lm 7805", "regulador 5v fijo", "voltage_regulator"],
    pins=make_pins(["IN", "GND", "OUT"], left_count=1, power={"IN", "OUT"}),
    footprint=FootprintDef(width_mm=10.5, height_mm=14.0, package="TO-220"),
    symbol_3d=Symbol3DDef(geometry="box", width_mm=10.5, height_mm=14.0, depth_mm=4.5, color_hex="#111111", details={"tab": True}),
    voltage_min=7.0,
    voltage_max=35.0,
    current_ma=1000.0,
    criticals=["Requiere capacitores de entrada y salida; disipar calor segun Vin e Iout."],
)

LM317 = ComponentDef(
    type="lm317",
    name="LM317 Adjustable Linear Regulator",
    category="power",
    aliases=["lm317", "lm 317", "regulador ajustable", "regulador lineal variable"],
    pins=make_pins(["ADJ", "OUT", "IN"], left_count=1, power={"IN", "OUT"}),
    footprint=FootprintDef(width_mm=10.5, height_mm=14.0, package="TO-220"),
    symbol_3d=Symbol3DDef(geometry="box", width_mm=10.5, height_mm=14.0, depth_mm=4.5, color_hex="#111111", details={"tab": True}),
    voltage_min=3.0,
    voltage_max=40.0,
    current_ma=1500.0,
    criticals=["Requiere red de ajuste y capacitores de estabilidad."],
)

AMS1117 = ComponentDef(
    type="ams1117",
    name="AMS1117 LDO Regulator",
    category="power",
    aliases=["ams1117", "ams 1117", "ldo 3.3v", "1117"],
    pins=make_pins(["GND", "OUT", "IN"], left_count=1, power={"IN", "OUT"}),
    footprint=FootprintDef(width_mm=5.0, height_mm=4.5, package="SOT-223", pad_pitch_mm=2.3),
    symbol_3d=Symbol3DDef(geometry="box", width_mm=5.0, height_mm=1.8, depth_mm=4.5, color_hex="#222222", details={"smd": True, "tab": True}),
    voltage_min=4.5,
    voltage_max=15.0,
    current_ma=800.0,
    criticals=["El margen termico limita la corriente; usar capacitores cerca del regulador."],
)
