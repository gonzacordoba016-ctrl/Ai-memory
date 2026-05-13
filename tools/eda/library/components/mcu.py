"""MCU and development-board component definitions."""
from __future__ import annotations

from tools.eda.library.base import ComponentDef, FootprintDef, Symbol3DDef, make_pins


ESP32 = ComponentDef(
    type="esp32",
    name="ESP32 DevKit V1",
    category="mcu",
    aliases=["esp-32", "esp32 wroom", "esp32_wroom_32", "esp32_devkit_v1", "esp32devkit"],
    pins=make_pins(
        [
            "3V3", "GND", "VIN", "EN", "GPIO36", "GPIO39", "GPIO34", "GPIO35",
            "GPIO32", "GPIO33", "GPIO25", "GPIO26", "GPIO27", "GPIO14", "GPIO12",
            "GPIO13", "GPIO23", "GPIO22", "GPIO21", "GPIO19", "GPIO18", "GPIO5",
            "GPIO17", "GPIO16", "GPIO4", "GPIO2", "GPIO15",
        ],
        left_count=14,
        power={"3V3", "VIN", "EN"},
    ),
    footprint=FootprintDef(width_mm=25.5, height_mm=48.0, package="MODULE", is_module=True),
    symbol_3d=Symbol3DDef(
        geometry="module",
        width_mm=25.5,
        height_mm=4.0,
        depth_mm=48.0,
        color_hex="#0a1f3a",
        details={"shield": True, "shield_color": "#888888", "usb": True, "pin_rows": 2},
    ),
    voltage_min=3.3,
    voltage_max=5.0,
    current_ma=240.0,
    criticals=[
        "Con WiFi activo no usar ADC2 para mediciones analogicas.",
        "Evitar pines de boot strap para senales que cambian durante reset.",
    ],
)

ESP8266 = ComponentDef(
    type="esp8266",
    name="ESP8266 NodeMCU",
    category="mcu",
    aliases=["nodemcu", "nodemcu v1", "esp-12", "esp12", "modulo wifi", "módulo wifi"],
    pins=make_pins(
        ["3V3", "GND", "VIN", "EN", "RST", "A0", "D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "RX", "TX"],
        left_count=8,
        power={"3V3", "VIN", "EN", "RST"},
    ),
    footprint=FootprintDef(width_mm=24.8, height_mm=16.0, package="MODULE", is_module=True),
    symbol_3d=Symbol3DDef(
        geometry="module",
        width_mm=24.8,
        height_mm=3.5,
        depth_mm=16.0,
        color_hex="#0a1f3a",
        details={"shield": True, "antenna": True, "pin_rows": 2},
    ),
    voltage_min=3.3,
    voltage_max=5.0,
    current_ma=170.0,
)

ARDUINO_UNO = ComponentDef(
    type="arduino_uno",
    name="Arduino Uno R3",
    category="mcu",
    aliases=["arduino", "uno", "arduino uno", "arduino_uno_r3"],
    pins=make_pins(
        ["VIN", "5V", "3V3", "GND", "RESET", "A0", "A1", "A2", "A3", "A4", "A5", "D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10", "D11", "D12", "D13"],
        left_count=11,
        power={"VIN", "5V", "3V3", "RESET"},
    ),
    footprint=FootprintDef(width_mm=68.6, height_mm=53.4, package="ARDUINO_UNO", is_module=True),
    symbol_3d=Symbol3DDef(geometry="module", width_mm=68.6, height_mm=12.0, depth_mm=53.4, color_hex="#006c78", details={"usb": True, "headers": 4}),
    voltage_min=5.0,
    voltage_max=12.0,
    current_ma=50.0,
)

ARDUINO_NANO = ComponentDef(
    type="arduino_nano",
    name="Arduino Nano",
    category="mcu",
    aliases=["nano", "arduino nano"],
    pins=make_pins(
        ["VIN", "5V", "3V3", "GND", "RESET", "A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7", "D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10", "D11", "D12", "D13"],
        left_count=14,
        power={"VIN", "5V", "3V3", "RESET"},
    ),
    footprint=FootprintDef(width_mm=18.0, height_mm=43.2, package="MODULE", is_module=True),
    symbol_3d=Symbol3DDef(geometry="module", width_mm=18.0, height_mm=8.0, depth_mm=43.2, color_hex="#006c78", details={"usb": True, "pin_rows": 2}),
    voltage_min=5.0,
    voltage_max=12.0,
    current_ma=45.0,
)

ARDUINO_MEGA = ComponentDef(
    type="arduino_mega",
    name="Arduino Mega 2560",
    category="mcu",
    aliases=["mega", "arduino mega", "arduino_mega2560"],
    pins=make_pins(
        ["VIN", "5V", "3V3", "GND", "RESET", "A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "A10", "A11", "A12", "A13", "A14", "A15", "D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10", "D11", "D12", "D13", "D20", "D21", "D50", "D51", "D52", "D53"],
        left_count=20,
        power={"VIN", "5V", "3V3", "RESET"},
    ),
    footprint=FootprintDef(width_mm=101.5, height_mm=53.4, package="ARDUINO_MEGA", is_module=True),
    symbol_3d=Symbol3DDef(geometry="module", width_mm=101.5, height_mm=12.0, depth_mm=53.4, color_hex="#006c78", details={"usb": True, "headers": 6}),
    voltage_min=5.0,
    voltage_max=12.0,
    current_ma=70.0,
)

STM32 = ComponentDef(
    type="stm32",
    name="STM32 Blue Pill",
    category="mcu",
    aliases=["blue pill", "stm32f103", "bluepill"],
    pins=make_pins(
        ["3V3", "5V", "GND", "VBAT", "NRST", "PA0", "PA1", "PA2", "PA3", "PA4", "PA5", "PA6", "PA7", "PB0", "PB1", "PB6", "PB7", "PB10", "PB11", "PC13", "PA9", "PA10"],
        left_count=11,
        power={"3V3", "5V", "VBAT", "NRST"},
    ),
    footprint=FootprintDef(width_mm=25.4, height_mm=25.4, package="MODULE", is_module=True),
    symbol_3d=Symbol3DDef(geometry="module", width_mm=25.4, height_mm=6.0, depth_mm=25.4, color_hex="#173b8e", details={"usb": True, "pin_rows": 2}),
    voltage_min=3.3,
    voltage_max=5.0,
    current_ma=80.0,
)

PICO = ComponentDef(
    type="raspberry_pi_pico",
    name="Raspberry Pi Pico",
    category="mcu",
    aliases=["pico", "rp2040", "raspberry pi pico", "raspberry_pi_pico"],
    pins=make_pins(
        ["VSYS", "VBUS", "3V3", "GND", "RUN", "GP0", "GP1", "GP2", "GP3", "GP4", "GP5", "GP6", "GP7", "GP8", "GP9", "GP10", "GP11", "GP12", "GP13", "GP14", "GP15", "GP16", "GP17", "GP18", "GP19", "GP20", "GP21", "GP22", "GP26", "GP27", "GP28"],
        left_count=15,
        power={"VSYS", "VBUS", "3V3", "RUN"},
    ),
    footprint=FootprintDef(width_mm=21.0, height_mm=51.0, package="MODULE", is_module=True),
    symbol_3d=Symbol3DDef(geometry="module", width_mm=21.0, height_mm=7.0, depth_mm=51.0, color_hex="#176b47", details={"usb": True, "pin_rows": 2}),
    voltage_min=3.3,
    voltage_max=5.0,
    current_ma=90.0,
)
