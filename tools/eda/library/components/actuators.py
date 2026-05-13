"""Actuator and driver component definitions."""
from __future__ import annotations

from tools.eda.library.base import ComponentDef, FootprintDef, Symbol3DDef, make_pins


RELAY_MODULE = ComponentDef(
    type="relay_module",
    name="1-Channel Relay Module",
    category="actuator",
    aliases=["relay_module", "relay", "rele", "relé", "modulo relay"],
    pins=make_pins(["VCC", "GND", "IN", "COM", "NO", "NC"], left_count=3, power={"VCC", "COM", "NO", "NC"}),
    footprint=FootprintDef(width_mm=40.0, height_mm=25.0, package="MODULE", is_module=True),
    symbol_3d=Symbol3DDef(geometry="module", width_mm=40.0, height_mm=17.0, depth_mm=25.0, color_hex="#1a5c1a", details={"relay_block": True, "terminal_block": True, "led": True}),
    voltage_min=5.0,
    voltage_max=5.0,
    current_ma=75.0,
    criticals=["Nunca mezclar tierra de potencia AC con tierra logica sin aislamiento adecuado."],
)

SERVO = ComponentDef(
    type="servo",
    name="RC Servo",
    category="actuator",
    aliases=["servo", "servo motor", "sg90", "mg996r", "motor servo"],
    pins=make_pins(["GND", "VCC", "SIGNAL"], left_count=1, power={"VCC"}),
    footprint=FootprintDef(width_mm=7.6, height_mm=2.54, package="SERVO_HEADER", is_module=True),
    symbol_3d=Symbol3DDef(geometry="box", width_mm=32.0, height_mm=30.0, depth_mm=12.0, color_hex="#1f4fa3", details={"horn": True, "three_wire_cable": True}),
    voltage_min=4.8,
    voltage_max=6.0,
    current_ma=650.0,
    criticals=["Servos medianos o grandes requieren fuente externa, no alimentarlos desde el pin 5V del MCU."],
)

L298N = ComponentDef(
    type="l298n",
    name="L298N Dual H-Bridge Driver Module",
    category="actuator",
    aliases=["l298n", "l298", "driver motor", "puente h", "h-bridge"],
    pins=make_pins(["VMS", "5V", "GND", "ENA", "IN1", "IN2", "IN3", "IN4", "ENB", "OUT1", "OUT2", "OUT3", "OUT4"], left_count=6, power={"VMS", "5V", "OUT1", "OUT2", "OUT3", "OUT4"}),
    footprint=FootprintDef(width_mm=43.0, height_mm=43.0, package="MODULE", is_module=True),
    symbol_3d=Symbol3DDef(geometry="module", width_mm=43.0, height_mm=18.0, depth_mm=43.0, color_hex="#b01717", details={"heatsink": True, "terminal_blocks": 3}),
    voltage_min=5.0,
    voltage_max=35.0,
    current_ma=2000.0,
    criticals=["Corriente maxima aproximada 2A por canal con disipacion adecuada."],
)

A4988 = ComponentDef(
    type="a4988",
    name="A4988 Stepper Driver Carrier",
    category="actuator",
    aliases=["a4988", "a 4988", "pololu stepper"],
    pins=make_pins(["VMOT", "GND", "2B", "2A", "1A", "1B", "VDD", "GND", "STEP", "DIR", "RESET", "SLEEP", "MS3", "MS2", "MS1", "ENABLE"], left_count=8, power={"VMOT", "VDD", "1A", "1B", "2A", "2B"}),
    footprint=FootprintDef(width_mm=15.2, height_mm=20.3, package="MODULE", is_module=True),
    symbol_3d=Symbol3DDef(geometry="module", width_mm=15.2, height_mm=5.0, depth_mm=20.3, color_hex="#7f1d1d", details={"potentiometer": True, "heatsink_optional": True, "pin_rows": 2}),
    voltage_min=3.3,
    voltage_max=5.0,
    current_ma=1000.0,
    criticals=["Colocar capacitor bulk de 100uF o mas entre VMOT y GND cerca del modulo.", "Ajustar limite de corriente antes de conectar el motor."],
)

DRV8825 = ComponentDef(
    type="drv8825",
    name="DRV8825 Stepper Driver Carrier",
    category="actuator",
    aliases=["drv8825", "drv 8825", "stepper driver", "driver paso a paso"],
    pins=make_pins(["VMOT", "GND", "B2", "B1", "A1", "A2", "FAULT", "GND", "VDD", "ENABLE", "M0", "M1", "M2", "RESET", "SLEEP", "STEP", "DIR"], left_count=8, power={"VMOT", "VDD", "A1", "A2", "B1", "B2"}),
    footprint=FootprintDef(width_mm=15.2, height_mm=20.3, package="MODULE", is_module=True),
    symbol_3d=Symbol3DDef(geometry="module", width_mm=15.2, height_mm=5.0, depth_mm=20.3, color_hex="#6d28d9", details={"potentiometer": True, "heatsink_optional": True, "pin_rows": 2}),
    voltage_min=3.3,
    voltage_max=5.0,
    current_ma=1500.0,
    criticals=["Colocar capacitor bulk de 100uF o mas entre VMOT y GND cerca del modulo.", "Ajustar limite de corriente antes de conectar el motor."],
)
