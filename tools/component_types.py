# Shared component type sets — single source of truth for schematic_renderer and pcb_renderer.

_MCU_TYPES = {"arduino_uno", "arduino_nano", "arduino_mega", "esp32", "esp8266",
              "stm32", "rp2040", "pico", "attiny", "mcu"}

_RELAY_TYPES = {"relay", "relay_module", "ssr"}

_ZONE_SENSOR_TYPES = {
    # I2C sensors
    "bmp280", "bme280", "bmp180", "bmp085",
    "mpu6050", "mpu9250", "icm20600", "icm42688",
    "ina219", "ina226", "ina260", "ads1115", "ads1015",
    "si7021", "htu21d", "sht31", "sht30", "aht20",
    "ds3231", "ds1307", "pcf8574",
    "vl53l0x", "tof", "apds9960",
    # 1-wire / analog sensors
    "ds18b20", "ds18s20", "lm35", "ntc", "thermistor",
    "dht22", "dht11", "am2302",
    # SPI sensors
    "max6675", "max31855", "max31865",
    "mcp3208", "mcp3204", "mcp3008",
    "nrf24l01",
    # Generic sensor modules
    "sensor", "moisture_sensor", "soil_sensor",
    "pir", "motion_sensor",
    "gas_sensor", "mq2", "mq135",
    "ultrasonic", "hc_sr04", "ultrasonic_sensor",
    "ir_sensor", "color_sensor",
}
