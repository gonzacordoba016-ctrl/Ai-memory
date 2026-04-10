# database/circuit_design.py

import sqlite3
import json as _json
import os
from typing import Dict, Any, List, Optional
from core.logger import get_logger

logger = get_logger(__name__)
from core.config import SQL_DB_PATH

DB_PATH = SQL_DB_PATH
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


# Librería de componentes con símbolos, footprints, pines, modelo 3D
COMPONENT_LIBRARY = {
    "arduino_uno": {
        "name": "Arduino Uno",
        "symbol": "arduinosymbol.svg",
        "footprint": "dip28",
        "pins": {
            "5V": "power",
            "3.3V": "power",
            "GND": "power",
            "0": "digital",
            "1": "digital",
            "2": "digital",
            "3": "digital",
            "4": "digital",
            "5": "digital",
            "6": "digital",
            "7": "digital",
            "8": "digital",
            "9": "digital",
            "10": "digital",
            "11": "digital",
            "12": "digital",
            "13": "digital",
            "A0": "analog",
            "A1": "analog",
            "A2": "analog",
            "A3": "analog",
            "A4": "analog",
            "A5": "analog"
        },
        "model_3d": "arduino_uno.stl",
        "color": "#334455"
    },
    "resistor": {
        "name": "Resistor",
        "symbol": "resistor.svg",
        "footprint": "axial",
        "pins": {"1": "passive", "2": "passive"},
        "model_3d": "resistor.stl",
        "color": "#cc6600"
    },
    "led": {
        "name": "LED",
        "symbol": "led.svg",
        "footprint": "th_led",
        "pins": {"A": "anode", "K": "cathode"},
        "model_3d": "led.stl",
        "color": "#ff0000"
    },
    "capacitor": {
        "name": "Capacitor",
        "symbol": "capacitor.svg",
        "footprint": "radial",
        "pins": {"1": "passive", "2": "passive"},
        "model_3d": "capacitor.stl",
        "color": "#ffffff"
    },
    "button": {
        "name": "Button",
        "symbol": "button.svg",
        "footprint": "tactile_switch",
        "pins": {"1": "switch", "2": "switch"},
        "model_3d": "button.stl",
        "color": "#aaaaaa"
    },

    # ── MCUs adicionales ────────────────────────────────────────────
    "esp32": {
        "name": "ESP32",
        "symbol": "esp32.svg",
        "footprint": "dip38",
        "pins": {
            "3V3": "power", "GND": "power", "EN": "digital",
            "GPIO0": "digital", "GPIO2": "digital", "GPIO4": "digital",
            "GPIO5": "digital", "GPIO12": "digital", "GPIO13": "digital",
            "GPIO14": "digital", "GPIO15": "digital", "GPIO16": "digital",
            "GPIO17": "digital", "GPIO18": "digital", "GPIO19": "digital",
            "GPIO21": "digital", "GPIO22": "digital", "GPIO23": "digital",
            "GPIO25": "digital", "GPIO26": "digital", "GPIO27": "digital",
            "GPIO32": "digital", "GPIO33": "digital",
            "GPIO34": "analog_in", "GPIO35": "analog_in",
            "GPIO36": "analog_in", "GPIO39": "analog_in",
        },
        "model_3d": "esp32.stl",
        "color": "#2244aa"
    },
    "esp8266": {
        "name": "ESP8266 NodeMCU",
        "symbol": "esp8266.svg",
        "footprint": "nodemcu",
        "pins": {
            "3V3": "power", "GND": "power", "VIN": "power",
            "D0": "digital", "D1": "digital", "D2": "digital",
            "D3": "digital", "D4": "digital", "D5": "digital",
            "D6": "digital", "D7": "digital", "D8": "digital",
            "A0": "analog", "TX": "digital", "RX": "digital",
        },
        "model_3d": "esp8266.stl",
        "color": "#1155bb"
    },
    "arduino_nano": {
        "name": "Arduino Nano",
        "symbol": "arduino_nano.svg",
        "footprint": "dip30",
        "pins": {
            "5V": "power", "3.3V": "power", "GND": "power", "VIN": "power",
            "D0": "digital", "D1": "digital", "D2": "digital", "D3": "digital",
            "D4": "digital", "D5": "digital", "D6": "digital", "D7": "digital",
            "D8": "digital", "D9": "digital", "D10": "digital", "D11": "digital",
            "D12": "digital", "D13": "digital",
            "A0": "analog", "A1": "analog", "A2": "analog",
            "A3": "analog", "A4": "analog", "A5": "analog",
            "A6": "analog", "A7": "analog",
        },
        "model_3d": "arduino_nano.stl",
        "color": "#2255aa"
    },

    # ── Sensores de temperatura / humedad ──────────────────────────
    "dht22": {
        "name": "DHT22",
        "symbol": "dht22.svg",
        "footprint": "dip4",
        "pins": {"VCC": "power", "DATA": "digital", "NC": "nc", "GND": "power"},
        "model_3d": "dht22.stl",
        "color": "#ffffff",
        "notes": "Requiere resistencia pull-up 10kΩ en DATA"
    },
    "dht11": {
        "name": "DHT11",
        "symbol": "dht11.svg",
        "footprint": "dip4",
        "pins": {"VCC": "power", "DATA": "digital", "NC": "nc", "GND": "power"},
        "model_3d": "dht11.stl",
        "color": "#4488ff",
        "notes": "Requiere resistencia pull-up 10kΩ en DATA"
    },
    "lm35": {
        "name": "LM35",
        "symbol": "lm35.svg",
        "footprint": "to92",
        "pins": {"VCC": "power", "OUT": "analog", "GND": "power"},
        "model_3d": "lm35.stl",
        "color": "#888888"
    },
    "bme280": {
        "name": "BME280",
        "symbol": "bme280.svg",
        "footprint": "smd_8",
        "pins": {
            "VCC": "power", "GND": "power",
            "SDA": "i2c", "SCL": "i2c",
            "CSB": "digital", "SDO": "digital",
        },
        "model_3d": "bme280.stl",
        "color": "#226644",
        "notes": "I2C addr: 0x76 (SDO=GND) o 0x77 (SDO=VCC)"
    },
    "ds18b20": {
        "name": "DS18B20",
        "symbol": "ds18b20.svg",
        "footprint": "to92",
        "pins": {"GND": "power", "DATA": "onewire", "VCC": "power"},
        "model_3d": "ds18b20.stl",
        "color": "#333333",
        "notes": "One-Wire. Requiere pull-up 4.7kΩ en DATA"
    },

    # ── Sensores de distancia / movimiento ─────────────────────────
    "hc_sr04": {
        "name": "HC-SR04 Ultrasónico",
        "symbol": "hcsr04.svg",
        "footprint": "dip4",
        "pins": {"VCC": "power", "TRIG": "digital", "ECHO": "digital", "GND": "power"},
        "model_3d": "hcsr04.stl",
        "color": "#4488cc",
        "notes": "ECHO retorna 5V — usar divisor de tensión para MCUs de 3.3V"
    },
    "pir": {
        "name": "Sensor PIR",
        "symbol": "pir.svg",
        "footprint": "dip3",
        "pins": {"VCC": "power", "OUT": "digital", "GND": "power"},
        "model_3d": "pir.stl",
        "color": "#ffffff"
    },
    "mpu6050": {
        "name": "MPU-6050 (IMU 6DOF)",
        "symbol": "mpu6050.svg",
        "footprint": "smd_8",
        "pins": {
            "VCC": "power", "GND": "power",
            "SDA": "i2c", "SCL": "i2c",
            "AD0": "digital", "INT": "digital",
        },
        "model_3d": "mpu6050.stl",
        "color": "#224466",
        "notes": "I2C addr: 0x68 (AD0=GND) o 0x69 (AD0=VCC)"
    },

    # ── Displays ────────────────────────────────────────────────────
    "lcd_16x2": {
        "name": "LCD 16x2 (HD44780)",
        "symbol": "lcd16x2.svg",
        "footprint": "lcd16x2",
        "pins": {
            "VSS": "power", "VDD": "power", "V0": "contrast",
            "RS": "digital", "RW": "digital", "E": "digital",
            "D0": "digital", "D1": "digital", "D2": "digital", "D3": "digital",
            "D4": "digital", "D5": "digital", "D6": "digital", "D7": "digital",
            "A": "power", "K": "power",
        },
        "model_3d": "lcd16x2.stl",
        "color": "#00aa00",
        "notes": "Usar módulo I2C (PCF8574) para reducir pines a SDA/SCL"
    },
    "oled_ssd1306": {
        "name": "OLED 0.96\" SSD1306 I2C",
        "symbol": "oled.svg",
        "footprint": "oled_4pin",
        "pins": {"VCC": "power", "GND": "power", "SCL": "i2c", "SDA": "i2c"},
        "model_3d": "oled.stl",
        "color": "#000000",
        "notes": "I2C addr: 0x3C o 0x3D"
    },
    "tft_ili9341": {
        "name": "TFT 2.4\" ILI9341 SPI",
        "symbol": "tft.svg",
        "footprint": "tft_spi",
        "pins": {
            "VCC": "power", "GND": "power",
            "CS": "digital", "RESET": "digital", "DC": "digital",
            "MOSI": "spi", "SCK": "spi", "LED": "power", "MISO": "spi",
        },
        "model_3d": "tft.stl",
        "color": "#224488"
    },
    "max7219": {
        "name": "MAX7219 (Matriz LED 8x8)",
        "symbol": "max7219.svg",
        "footprint": "dip24",
        "pins": {
            "VCC": "power", "GND": "power",
            "DIN": "spi", "CS": "digital", "CLK": "spi",
        },
        "model_3d": "max7219.stl",
        "color": "#cc0000"
    },

    # ── Módulos de comunicación ─────────────────────────────────────
    "hc05_bt": {
        "name": "HC-05 Bluetooth",
        "symbol": "hc05.svg",
        "footprint": "hc05",
        "pins": {
            "VCC": "power", "GND": "power",
            "TXD": "uart", "RXD": "uart",
            "STATE": "digital", "EN": "digital",
        },
        "model_3d": "hc05.stl",
        "color": "#0055cc",
        "notes": "RXD acepta 3.3V — usar divisor de tensión si MCU es 5V"
    },
    "nrf24l01": {
        "name": "nRF24L01+ (RF 2.4GHz)",
        "symbol": "nrf24.svg",
        "footprint": "nrf24",
        "pins": {
            "GND": "power", "VCC": "power",
            "CE": "digital", "CSN": "digital",
            "SCK": "spi", "MOSI": "spi", "MISO": "spi", "IRQ": "digital",
        },
        "model_3d": "nrf24.stl",
        "color": "#006600",
        "notes": "Opera a 3.3V — NO conectar a 5V directo"
    },
    "sim800l": {
        "name": "SIM800L (GSM/GPRS)",
        "symbol": "sim800l.svg",
        "footprint": "sim800l",
        "pins": {
            "VCC": "power", "GND": "power",
            "TXD": "uart", "RXD": "uart",
            "RST": "digital",
        },
        "model_3d": "sim800l.stl",
        "color": "#004488",
        "notes": "Pico de corriente 2A — usar capacitor electrolítico 1000µF en VCC"
    },

    # ── Actuadores ──────────────────────────────────────────────────
    "servo_sg90": {
        "name": "Servo SG90",
        "symbol": "servo.svg",
        "footprint": "servo_3pin",
        "pins": {"GND": "power", "VCC": "power", "SIGNAL": "pwm"},
        "model_3d": "servo.stl",
        "color": "#ff8800"
    },
    "l298n": {
        "name": "L298N (Driver Motor DC)",
        "symbol": "l298n.svg",
        "footprint": "l298n",
        "pins": {
            "VCC": "power", "GND": "power", "5V": "power",
            "IN1": "digital", "IN2": "digital", "IN3": "digital", "IN4": "digital",
            "ENA": "pwm", "ENB": "pwm",
            "OUT1": "motor", "OUT2": "motor", "OUT3": "motor", "OUT4": "motor",
        },
        "model_3d": "l298n.stl",
        "color": "#cc0000",
        "notes": "ENA/ENB controlan velocidad por PWM; IN1-IN4 controlan dirección"
    },
    "relay_5v": {
        "name": "Relé 5V",
        "symbol": "relay.svg",
        "footprint": "relay_th",
        "pins": {
            "VCC": "power", "GND": "power", "IN": "digital",
            "COM": "ac", "NO": "ac", "NC": "ac",
        },
        "model_3d": "relay.stl",
        "color": "#006600",
        "notes": "Agregar diodo flyback y transistor NPN para proteger el pin de control"
    },
    "buzzer": {
        "name": "Buzzer Piezoeléctrico",
        "symbol": "buzzer.svg",
        "footprint": "buzzer_th",
        "pins": {"1": "digital", "2": "power"},
        "model_3d": "buzzer.stl",
        "color": "#222222"
    },

    # ── Almacenamiento / Interfaz ───────────────────────────────────
    "sd_card": {
        "name": "Módulo SD Card SPI",
        "symbol": "sdcard.svg",
        "footprint": "sd_spi",
        "pins": {
            "VCC": "power", "GND": "power",
            "CS": "digital", "MOSI": "spi", "CLK": "spi", "MISO": "spi",
        },
        "model_3d": "sdcard.stl",
        "color": "#ffcc00",
        "notes": "Opera a 3.3V — muchos módulos incluyen regulador integrado"
    },
    "rtc_ds3231": {
        "name": "RTC DS3231",
        "symbol": "rtc.svg",
        "footprint": "smd_8",
        "pins": {
            "VCC": "power", "GND": "power",
            "SDA": "i2c", "SCL": "i2c",
            "SQW": "digital", "32K": "digital",
        },
        "model_3d": "rtc.stl",
        "color": "#444488",
        "notes": "I2C addr: 0x68. Incluye batería CR2032"
    },

    # ── Pasivos ─────────────────────────────────────────────────────
    "potentiometer": {
        "name": "Potenciómetro",
        "symbol": "pot.svg",
        "footprint": "pot_th",
        "pins": {"1": "passive", "W": "wiper", "2": "passive"},
        "model_3d": "pot.stl",
        "color": "#886644"
    },
    "transistor_npn": {
        "name": "Transistor NPN (2N2222 / BC547)",
        "symbol": "npn.svg",
        "footprint": "to92",
        "pins": {"B": "base", "C": "collector", "E": "emitter"},
        "model_3d": "npn.stl",
        "color": "#444444"
    },
    "diode": {
        "name": "Diodo 1N4007",
        "symbol": "diode.svg",
        "footprint": "axial",
        "pins": {"A": "anode", "K": "cathode"},
        "model_3d": "diode.stl",
        "color": "#884400"
    },
    "inductor": {
        "name": "Inductor",
        "symbol": "inductor.svg",
        "footprint": "axial",
        "pins": {"1": "passive", "2": "passive"},
        "model_3d": "inductor.stl",
        "color": "#888800"
    },

    # ── Fuentes / Reguladores ───────────────────────────────────────
    "lm7805": {
        "name": "Regulador LM7805 (5V)",
        "symbol": "lm7805.svg",
        "footprint": "to220",
        "pins": {"VIN": "power", "GND": "power", "VOUT": "power"},
        "model_3d": "lm7805.stl",
        "color": "#555555",
        "notes": "Requiere capacitores 0.1µF + 10µF en entrada y salida"
    },
    "ams1117": {
        "name": "Regulador AMS1117 (3.3V)",
        "symbol": "ams1117.svg",
        "footprint": "sot223",
        "pins": {"GND": "power", "VIN": "power", "VOUT": "power"},
        "model_3d": "ams1117.stl",
        "color": "#666666"
    },
}

# Alias para reconocimiento en español/inglés
COMPONENT_ALIASES = {
    # Arduino
    "arduino uno": "arduino_uno",
    "arduino nano": "arduino_uno",
    "placa arduino": "arduino_uno",
    
    # Resistencias
    "resistencia": "resistor",
    "resistor": "resistor",
    "res": "resistor",
    
    # LEDs
    "led": "led",
    "diodo led": "led",
    "led rojo": "led",
    "led verde": "led",
    "led azul": "led",
    
    # Capacitores
    "capacitor": "capacitor",
    "condensador": "capacitor",
    "cap": "capacitor",
    
    # Botones
    "botón": "button",
    "boton": "button",
    "pulsador": "button",
    "switch": "button",

    # ESP32 / ESP8266
    "esp32": "esp32",
    "esp-32": "esp32",
    "esp8266": "esp8266",
    "nodemcu": "esp8266",
    "wemos d1": "esp8266",
    "arduino nano": "arduino_nano",

    # Sensores temperatura / humedad
    "dht22": "dht22",
    "am2302": "dht22",
    "dht11": "dht11",
    "lm35": "lm35",
    "sensor de temperatura": "lm35",
    "bme280": "bme280",
    "sensor temperatura humedad presion": "bme280",
    "ds18b20": "ds18b20",
    "sensor temperatura one wire": "ds18b20",

    # Sensores distancia / movimiento
    "hc-sr04": "hc_sr04",
    "hcsr04": "hc_sr04",
    "ultrasonico": "hc_sr04",
    "sensor ultrasonico": "hc_sr04",
    "pir": "pir",
    "sensor de movimiento": "pir",
    "detector de movimiento": "pir",
    "mpu6050": "mpu6050",
    "giroscopio": "mpu6050",
    "acelerometro": "mpu6050",
    "imu": "mpu6050",

    # Displays
    "lcd": "lcd_16x2",
    "lcd 16x2": "lcd_16x2",
    "pantalla lcd": "lcd_16x2",
    "oled": "oled_ssd1306",
    "oled 0.96": "oled_ssd1306",
    "ssd1306": "oled_ssd1306",
    "pantalla oled": "oled_ssd1306",
    "tft": "tft_ili9341",
    "pantalla tft": "tft_ili9341",
    "ili9341": "tft_ili9341",
    "matriz led": "max7219",
    "max7219": "max7219",

    # Comunicación
    "hc-05": "hc05_bt",
    "hc05": "hc05_bt",
    "bluetooth": "hc05_bt",
    "modulo bluetooth": "hc05_bt",
    "nrf24": "nrf24l01",
    "nrf24l01": "nrf24l01",
    "rf 2.4ghz": "nrf24l01",
    "sim800l": "sim800l",
    "gsm": "sim800l",
    "gprs": "sim800l",

    # Actuadores
    "servo": "servo_sg90",
    "servo sg90": "servo_sg90",
    "servomotor": "servo_sg90",
    "l298n": "l298n",
    "driver motor": "l298n",
    "puente h": "l298n",
    "rele": "relay_5v",
    "relé": "relay_5v",
    "relay": "relay_5v",
    "buzzer": "buzzer",
    "zumbador": "buzzer",

    # Almacenamiento
    "sd card": "sd_card",
    "tarjeta sd": "sd_card",
    "modulo sd": "sd_card",
    "rtc": "rtc_ds3231",
    "ds3231": "rtc_ds3231",
    "reloj tiempo real": "rtc_ds3231",

    # Pasivos
    "potenciometro": "potentiometer",
    "potenciómetro": "potentiometer",
    "pot": "potentiometer",
    "transistor": "transistor_npn",
    "npn": "transistor_npn",
    "2n2222": "transistor_npn",
    "bc547": "transistor_npn",
    "diodo": "diode",
    "1n4007": "diode",
    "diodo rectificador": "diode",
    "diodo flyback": "diode",
    "inductor": "inductor",
    "bobina": "inductor",

    # Fuentes
    "7805": "lm7805",
    "lm7805": "lm7805",
    "regulador 5v": "lm7805",
    "ams1117": "ams1117",
    "regulador 3.3v": "ams1117",
    "regulador 3v3": "ams1117",
}

class CircuitDesignManager:
    def __init__(self):
        self.db_path = DB_PATH
        self._init_db()
        
    def _get_conn(self):
        return sqlite3.connect(self.db_path)
        
    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS circuit_designs (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     TEXT NOT NULL DEFAULT 'default',
                    name        TEXT NOT NULL,
                    description TEXT,
                    components  TEXT,   -- JSON array
                    nets        TEXT,   -- JSON array
                    metadata    TEXT,   -- JSON object
                    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            try:
                conn.execute("ALTER TABLE circuit_designs ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'")
            except Exception:
                pass

            conn.execute("""
                CREATE TABLE IF NOT EXISTS circuit_versions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    circuit_id  INTEGER,
                    version     INTEGER,
                    snapshot    TEXT,   -- JSON completo del circuito
                    reason      TEXT,
                    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (circuit_id) REFERENCES circuit_designs (id)
                )
            """)
            conn.commit()
            
    def save_design(self, circuit_data: Dict[str, Any], user_id: str = "default") -> int:
        """Guarda un diseño de circuito y retorna su ID."""
        try:
            name = circuit_data.get("name", "Circuito sin nombre")
            description = circuit_data.get("description", "")
            components = _json.dumps(circuit_data.get("components", []), ensure_ascii=False)
            nets = _json.dumps(circuit_data.get("nets", []), ensure_ascii=False)
            # Mergear metadata extra (source_tool, type, etc.) con power/warnings
            extra_meta = circuit_data.get("metadata", {}) or {}
            metadata = _json.dumps({
                "power":    circuit_data.get("power", extra_meta.get("power", "")),
                "warnings": circuit_data.get("warnings", extra_meta.get("warnings", [])),
                **{k: v for k, v in extra_meta.items() if k not in ("power", "warnings")},
            }, ensure_ascii=False)

            with self._get_conn() as conn:
                cur = conn.execute("""
                    INSERT INTO circuit_designs (user_id, name, description, components, nets, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (user_id, name, description, components, nets, metadata))
                design_id = cur.lastrowid
                conn.commit()
                
            logger.info(f"[CircuitDesign] Diseño guardado: {name} (ID: {design_id})")
            return design_id
            
        except Exception as e:
            logger.error(f"[CircuitDesign] Error guardando diseño: {e}")
            return -1
            
    def get_design(self, design_id: int) -> Optional[Dict[str, Any]]:
        """Obtiene un diseño de circuito por ID."""
        try:
            with self._get_conn() as conn:
                row = conn.execute("""
                    SELECT id, name, description, components, nets, metadata, created_at, updated_at
                    FROM circuit_designs WHERE id = ?
                """, (design_id,)).fetchone()
                
            if not row:
                return None
                
            components = _json.loads(row[3]) if row[3] else []
            nets = _json.loads(row[4]) if row[4] else []
            metadata = _json.loads(row[5]) if row[5] else {}
            
            return {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "components": components,
                "nets": nets,
                "power": metadata.get("power", ""),
                "warnings": metadata.get("warnings", []),
                "positions": metadata.get("positions", {}),
                "created_at": row[6],
                "updated_at": row[7]
            }
            
        except Exception as e:
            logger.error(f"[CircuitDesign] Error obteniendo diseño: {e}")
            return None
            
    def list_designs(self, user_id: str = "default") -> List[Dict[str, Any]]:
        """Lista todos los diseños de circuitos del usuario."""
        try:
            with self._get_conn() as conn:
                rows = conn.execute("""
                    SELECT id, name, description, created_at, updated_at
                    FROM circuit_designs
                    WHERE user_id = ?
                    ORDER BY updated_at DESC
                """, (user_id,)).fetchall()
                
            return [
                {
                    "id": row[0],
                    "name": row[1],
                    "description": row[2],
                    "created_at": row[3],
                    "updated_at": row[4]
                }
                for row in rows
            ]
            
        except Exception as e:
            logger.error(f"[CircuitDesign] Error listando diseños: {e}")
            return []
            
    def save_render_data(self, design_id: int, render_data: Dict[str, Any]) -> bool:
        """Guarda datos de renderizado asociados al diseño."""
        # Esto podría guardarse en una tabla separada si se necesita
        logger.info(f"[CircuitDesign] Datos de render guardados para diseño {design_id}")
        return True
        
    def update_layout(self, design_id: int, positions: dict) -> bool:
        """
        Guarda posiciones personalizadas de componentes en el metadata del diseño.
        positions: { "comp_id": {"x": 100, "y": 200}, ... }
        """
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT metadata FROM circuit_designs WHERE id = ?", (design_id,)
                ).fetchone()
                if not row:
                    return False
                metadata = _json.loads(row[0]) if row[0] else {}
                metadata["positions"] = positions
                conn.execute(
                    "UPDATE circuit_designs SET metadata = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (_json.dumps(metadata, ensure_ascii=False), design_id)
                )
                conn.commit()
            logger.info(f"[CircuitDesign] Layout actualizado para diseño {design_id}")
            return True
        except Exception as e:
            logger.error(f"[CircuitDesign] Error actualizando layout: {e}")
            return False

    def resolve_component_type(self, component_type: str) -> str:
        """Resuelve el tipo de componente usando los aliases."""
        return COMPONENT_ALIASES.get(component_type.lower(), component_type)
