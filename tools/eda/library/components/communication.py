"""Communication module component definitions."""
from __future__ import annotations

from tools.eda.library.base import ComponentDef, FootprintDef, Symbol3DDef, make_pins


NRF24L01 = ComponentDef(
    type="nrf24l01",
    name="nRF24L01 2.4GHz Transceiver Module",
    category="communication",
    aliases=["nrf24l01", "nrf24", "2.4ghz transceiver", "nordic", "nrf"],
    pins=make_pins(["GND", "VCC", "CE", "CSN", "SCK", "MOSI", "MISO", "IRQ"], left_count=2, power={"VCC"}),
    footprint=FootprintDef(width_mm=15.0, height_mm=29.0, package="MODULE", is_module=True),
    symbol_3d=Symbol3DDef(geometry="module", width_mm=15.0, height_mm=3.0, depth_mm=29.0, color_hex="#1a5c1a", details={"antenna": "pcb", "pin_rows": 1}),
    voltage_min=1.9,
    voltage_max=3.6,
    current_ma=115.0,
    criticals=["No alimentar con 5V.", "Agregar capacitor local de 10uF-47uF para evitar resets de radio."],
)

HC05 = ComponentDef(
    type="hc05",
    name="HC-05 Bluetooth Serial Module",
    category="communication",
    aliases=["hc-05", "hc05", "hc 05", "bluetooth serial", "bt serial", "modulo bluetooth", "módulo bluetooth"],
    pins=make_pins(["VCC", "GND", "TXD", "RXD", "STATE", "EN"], left_count=2, power={"VCC", "EN"}),
    footprint=FootprintDef(width_mm=37.0, height_mm=16.0, package="MODULE", is_module=True),
    symbol_3d=Symbol3DDef(geometry="module", width_mm=37.0, height_mm=3.0, depth_mm=16.0, color_hex="#1f4fa3", details={"antenna": "pcb", "pin_rows": 1}),
    voltage_min=3.3,
    voltage_max=5.0,
    current_ma=40.0,
    criticals=["RXD del modulo tolera 3.3V; usar divisor si el MCU transmite a 5V."],
)
