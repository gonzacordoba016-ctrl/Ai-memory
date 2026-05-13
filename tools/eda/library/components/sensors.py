"""Sensor component definitions."""
from __future__ import annotations

from tools.eda.library.base import ComponentDef, FootprintDef, Symbol3DDef, make_pins


BMP280 = ComponentDef(
    type="bmp280",
    name="BMP280/BME280 Pressure Sensor",
    category="sensor",
    aliases=["bmp280", "bme280", "bmp 280", "bme 280", "presion barometrica"],
    pins=make_pins(["VCC", "GND", "SCL", "SDA", "CSB", "SDO"], left_count=2, power={"VCC"}),
    footprint=FootprintDef(width_mm=14.0, height_mm=14.0, package="MODULE", is_module=True),
    symbol_3d=Symbol3DDef(geometry="module", width_mm=14.0, height_mm=1.6, depth_mm=14.0, color_hex="#2d5a27", details={"chip": True}),
    voltage_min=1.8,
    voltage_max=3.6,
    current_ma=1.0,
)

DHT11 = ComponentDef(
    type="dht11",
    name="DHT11 Temperature/Humidity Sensor",
    category="sensor",
    aliases=["dht11", "dht 11"],
    pins=make_pins(["VCC", "DATA", "NC", "GND"], left_count=2, power={"VCC"}),
    footprint=FootprintDef(width_mm=12.0, height_mm=15.5, package="DHT", is_module=False),
    symbol_3d=Symbol3DDef(geometry="box", width_mm=12.0, height_mm=7.0, depth_mm=15.5, color_hex="#3c7bc7", details={"vents": True}),
    voltage_min=3.3,
    voltage_max=5.5,
    current_ma=2.5,
)

DHT22 = ComponentDef(
    type="dht22",
    name="DHT22 / AM2302 Temperature/Humidity Sensor",
    category="sensor",
    aliases=["dht22", "dht 22", "am2302", "dht"],
    pins=make_pins(["VCC", "DATA", "NC", "GND"], left_count=2, power={"VCC"}),
    footprint=FootprintDef(width_mm=15.5, height_mm=25.0, package="DHT", is_module=False),
    symbol_3d=Symbol3DDef(geometry="box", width_mm=15.5, height_mm=7.0, depth_mm=25.0, color_hex="#eeeeee", details={"vents": True}),
    voltage_min=3.3,
    voltage_max=6.0,
    current_ma=2.5,
    criticals=["Requiere pull-up de 4.7k-10k en DATA."],
)

DS18B20 = ComponentDef(
    type="ds18b20",
    name="DS18B20 1-Wire Temperature Sensor",
    category="sensor",
    aliases=["ds18b20", "18b20", "dallas temperature", "onewire temperatura"],
    pins=make_pins(["GND", "DQ", "VDD"], left_count=1, power={"VDD"}),
    footprint=FootprintDef(width_mm=5.0, height_mm=4.5, package="TO-92"),
    symbol_3d=Symbol3DDef(geometry="to92", width_mm=5.0, height_mm=4.5, depth_mm=4.5, color_hex="#111111", details={"flat_side": True}),
    voltage_min=3.0,
    voltage_max=5.5,
    current_ma=1.5,
)

DS3231 = ComponentDef(
    type="ds3231",
    name="DS3231 RTC Module",
    category="sensor",
    aliases=["ds3231", "ds 3231", "rtc", "reloj tiempo real", "real time clock", "ds1307"],
    pins=make_pins(["VCC", "GND", "SDA", "SCL", "SQW", "32K"], left_count=2, power={"VCC"}),
    footprint=FootprintDef(width_mm=38.0, height_mm=22.0, package="MODULE", is_module=True),
    symbol_3d=Symbol3DDef(geometry="module", width_mm=38.0, height_mm=6.5, depth_mm=22.0, color_hex="#1a5c1a", details={"battery": "CR2032", "crystal": True}),
    voltage_min=3.3,
    voltage_max=5.5,
    current_ma=2.0,
)

FC28 = ComponentDef(
    type="fc28",
    name="FC-28 Soil Moisture Sensor",
    category="sensor",
    aliases=["fc28", "fc-28", "yl-69", "yl69", "yl-83", "humedad suelo", "soil moisture", "moisture sensor", "moisture_sensor", "sensor lluvia"],
    pins=make_pins(["VCC", "GND", "AOUT", "DOUT"], left_count=2, power={"VCC"}),
    footprint=FootprintDef(width_mm=16.0, height_mm=60.0, package="MODULE", is_module=True),
    symbol_3d=Symbol3DDef(geometry="module", width_mm=16.0, height_mm=1.6, depth_mm=60.0, color_hex="#c58d38", details={"probe": True, "controller_board": True}),
    voltage_min=3.3,
    voltage_max=5.0,
    current_ma=35.0,
    criticals=["La sonda se corroe si queda alimentada continuamente en suelo humedo."],
)

HC_SR04 = ComponentDef(
    type="hc_sr04",
    name="HC-SR04 Ultrasonic Sensor",
    category="sensor",
    aliases=["hc-sr04", "hcsr04", "hc sr04", "ultrasonico", "ultrasonic", "sr04"],
    pins=make_pins(["VCC", "TRIG", "ECHO", "GND"], left_count=2, power={"VCC"}),
    footprint=FootprintDef(width_mm=45.0, height_mm=20.0, package="MODULE", is_module=True),
    symbol_3d=Symbol3DDef(geometry="module", width_mm=45.0, height_mm=14.0, depth_mm=20.0, color_hex="#1a5c1a", details={"transducers": 2}),
    voltage_min=5.0,
    voltage_max=5.0,
    current_ma=15.0,
    criticals=["ECHO es 5V; usar divisor o level shifter hacia MCUs de 3.3V."],
)

HX711 = ComponentDef(
    type="hx711",
    name="HX711 Load Cell Amplifier",
    category="sensor",
    aliases=["hx711", "hx 711", "celda de carga", "balanza", "load cell", "peso"],
    pins=make_pins(["VCC", "GND", "DT", "SCK", "E+", "E-", "A+", "A-"], left_count=4, power={"VCC", "E+", "E-"}),
    footprint=FootprintDef(width_mm=21.0, height_mm=34.0, package="MODULE", is_module=True),
    symbol_3d=Symbol3DDef(geometry="module", width_mm=21.0, height_mm=4.0, depth_mm=34.0, color_hex="#7b1f8a", details={"terminal_block": True}),
    voltage_min=2.6,
    voltage_max=5.5,
    current_ma=1.5,
)

INA219 = ComponentDef(
    type="ina219",
    name="INA219 Current Sensor",
    category="sensor",
    aliases=["ina219", "ina 219", "sensor corriente", "corriente i2c", "power monitor"],
    pins=make_pins(["VCC", "GND", "SDA", "SCL", "VIN+", "VIN-"], left_count=2, power={"VCC", "VIN+", "VIN-"}),
    footprint=FootprintDef(width_mm=10.0, height_mm=13.5, package="MODULE", is_module=True),
    symbol_3d=Symbol3DDef(geometry="module", width_mm=10.0, height_mm=3.0, depth_mm=13.5, color_hex="#2d5a27", details={"shunt": True}),
    voltage_min=3.0,
    voltage_max=5.5,
    current_ma=1.0,
)

MPU6050 = ComponentDef(
    type="mpu6050",
    name="MPU6050 IMU",
    category="sensor",
    aliases=["mpu6050", "mpu-6050", "mpu 6050", "acelerometro", "giroscopio", "imu"],
    pins=make_pins(["VCC", "GND", "SCL", "SDA", "XDA", "XCL", "AD0", "INT"], left_count=2, power={"VCC"}),
    footprint=FootprintDef(width_mm=20.0, height_mm=20.0, package="MODULE", is_module=True),
    symbol_3d=Symbol3DDef(geometry="module", width_mm=20.0, height_mm=3.0, depth_mm=20.0, color_hex="#1f5fbf", details={"chip": True, "mounting_holes": 2}),
    voltage_min=3.3,
    voltage_max=5.0,
    current_ma=3.9,
)

MQ2 = ComponentDef(
    type="mq2",
    name="MQ-2 Gas Sensor Module",
    category="sensor",
    aliases=["mq2", "mq-2", "mq 2", "sensor gas", "gas combustible", "gas sensor", "sensor humo", "sensor glp"],
    pins=make_pins(["VCC", "GND", "AOUT", "DOUT"], left_count=2, power={"VCC"}),
    footprint=FootprintDef(width_mm=36.0, height_mm=36.0, package="MODULE", is_module=True),
    symbol_3d=Symbol3DDef(geometry="cylinder", width_mm=18.0, height_mm=16.0, depth_mm=18.0, color_hex="#c8c8c8", details={"heater_can": True, "carrier": [36.0, 36.0]}),
    voltage_min=5.0,
    voltage_max=5.0,
    current_ma=160.0,
    criticals=["No usar como sistema de seguridad en atmosferas explosivas.", "Requiere pre-calentamiento para lectura estable."],
)

MQ7 = ComponentDef(
    type="mq7",
    name="MQ-7 Carbon Monoxide Sensor Module",
    category="sensor",
    aliases=["mq7", "mq-7", "mq 7", "sensor co", "sensor monoxido", "monoxido de carbono", "carbon monoxide"],
    pins=make_pins(["VCC", "GND", "AOUT", "DOUT"], left_count=2, power={"VCC"}),
    footprint=FootprintDef(width_mm=36.0, height_mm=36.0, package="MODULE", is_module=True),
    symbol_3d=Symbol3DDef(geometry="cylinder", width_mm=18.0, height_mm=16.0, depth_mm=18.0, color_hex="#c8c8c8", details={"heater_can": True, "carrier": [36.0, 36.0]}),
    voltage_min=5.0,
    voltage_max=5.0,
    current_ma=160.0,
    criticals=["No usar como sistema de seguridad en atmosferas explosivas.", "Requiere ciclo de calentamiento para medir CO."],
)

MQ135 = ComponentDef(
    type="mq135",
    name="MQ-135 Air Quality Sensor Module",
    category="sensor",
    aliases=["mq135", "mq-135", "mq 135", "calidad aire", "air quality", "sensor calidad aire"],
    pins=make_pins(["VCC", "GND", "AOUT", "DOUT"], left_count=2, power={"VCC"}),
    footprint=FootprintDef(width_mm=36.0, height_mm=36.0, package="MODULE", is_module=True),
    symbol_3d=Symbol3DDef(geometry="cylinder", width_mm=18.0, height_mm=16.0, depth_mm=18.0, color_hex="#c8c8c8", details={"heater_can": True, "carrier": [36.0, 36.0]}),
    voltage_min=5.0,
    voltage_max=5.0,
    current_ma=160.0,
    criticals=["No usar como sistema de seguridad en atmosferas explosivas.", "Requiere pre-calentamiento para lectura estable."],
)

PIR = ComponentDef(
    type="pir",
    name="HC-SR501 PIR Motion Sensor",
    category="sensor",
    aliases=["pir", "hc-sr501", "hc_sr501", "sensor movimiento", "detector movimiento", "motion sensor"],
    pins=make_pins(["VCC", "OUT", "GND"], left_count=1, power={"VCC"}),
    footprint=FootprintDef(width_mm=25.0, height_mm=35.0, package="MODULE", is_module=True),
    symbol_3d=Symbol3DDef(geometry="module", width_mm=25.0, height_mm=18.0, depth_mm=35.0, color_hex="#1a5c1a", details={"fresnel_lens": True}),
    voltage_min=5.0,
    voltage_max=12.0,
    current_ma=65.0,
)
