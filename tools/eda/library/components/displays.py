"""Display component definitions."""
from __future__ import annotations

from tools.eda.library.base import ComponentDef, FootprintDef, Symbol3DDef, make_pins


OLED_SSD1306 = ComponentDef(
    type="oled_ssd1306",
    name="SSD1306 OLED 128x64 I2C",
    category="display",
    aliases=["oled", "ssd1306", "oled 128x64", "oled i2c", "pantalla oled", "display_oled"],
    pins=make_pins(["GND", "VCC", "SCL", "SDA"], left_count=2, power={"VCC"}),
    footprint=FootprintDef(width_mm=27.0, height_mm=27.0, package="MODULE", is_module=True),
    symbol_3d=Symbol3DDef(geometry="module", width_mm=27.0, height_mm=2.0, depth_mm=27.0, color_hex="#111111", details={"screen": True, "screen_color": "#0033ff"}),
    voltage_min=3.3,
    voltage_max=5.0,
    current_ma=20.0,
)

LCD_I2C = ComponentDef(
    type="lcd_i2c",
    name="LCD 16x2 I2C",
    category="display",
    aliases=["lcd", "lcd_i2c", "lcd i2c", "lcd 16x2", "pantalla lcd", "liquidcrystal i2c", "liquid crystal"],
    pins=make_pins(["GND", "VCC", "SDA", "SCL"], left_count=2, power={"VCC"}),
    footprint=FootprintDef(width_mm=80.0, height_mm=36.0, package="MODULE", is_module=True),
    symbol_3d=Symbol3DDef(geometry="module", width_mm=80.0, height_mm=8.0, depth_mm=36.0, color_hex="#1f6f2a", details={"screen": True, "screen_color": "#9bc44d", "backpack": "pcf8574"}),
    voltage_min=5.0,
    voltage_max=5.0,
    current_ma=25.0,
    criticals=["Con 3.3V puede no encender el backlight; usar alimentacion de 5V o modulo compatible."],
)
