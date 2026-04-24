# tools/component_pinouts.py
# Static database of verified component pinouts injected into the LLM prompt
# BEFORE netlist generation — prevents pin hallucination and missing passives.

from __future__ import annotations
from typing import Optional

# ────────────────────────────────────────────────────────────────────────────
# DATABASE
# pins: {name: description}
# wiring_notes: critical passive/connection requirements
# critical_warnings: things that will break the circuit or destroy hardware
# voltage: operating voltage summary
# search_keys: substrings matched against the circuit description
# ────────────────────────────────────────────────────────────────────────────

PINOUTS: dict[str, dict] = {

    # ── SENSORS ──────────────────────────────────────────────────────────────

    "dht22": {
        "label": "DHT22 / AM2302 (temperatura+humedad)",
        "pins": {
            "VCC": "Alimentación 3.3V–5V",
            "DATA": "Señal digital — pull-up 10kΩ a VCC obligatorio",
            "NC":   "No conectar",
            "GND":  "Tierra",
        },
        "wiring_notes": [
            "Resistencia pull-up 10kΩ entre DATA y VCC — sin ella lecturas siempre NaN",
            "Cap 100nF entre VCC y GND cerca del sensor para estabilidad",
        ],
        "critical_warnings": [
            "SIN pull-up 10kΩ en DATA el bus flota → lecturas NaN constantes",
        ],
        "voltage": "3.3V–5V",
        "search_keys": ["dht22", "dht 22", "am2302", "dht"],
    },

    "dht11": {
        "label": "DHT11 (temperatura+humedad básico)",
        "pins": {
            "VCC": "Alimentación 3.3V–5V",
            "DATA": "Señal digital — pull-up 10kΩ a VCC obligatorio",
            "NC":   "No conectar",
            "GND":  "Tierra",
        },
        "wiring_notes": [
            "Pull-up 10kΩ entre DATA y VCC — obligatoria",
        ],
        "critical_warnings": [],
        "voltage": "3.3V–5V",
        "search_keys": ["dht11", "dht 11"],
    },

    "ds18b20": {
        "label": "DS18B20 (temperatura One-Wire)",
        "pins": {
            "GND": "Tierra",
            "DQ":  "Bus One-Wire — pull-up 4.7kΩ a VCC obligatorio",
            "VDD": "Alimentación 3.3V–5.5V (o GND en modo parásito)",
        },
        "wiring_notes": [
            "Pull-up 4.7kΩ entre DQ y VCC — un solo pull-up para múltiples sensores en el mismo bus",
            "Modo parásito (VDD a GND): pull-up más fuerte 2.2kΩ o transistor en DQ",
        ],
        "critical_warnings": [
            "SIN pull-up en DQ el bus nunca sube → sensor no responde",
        ],
        "voltage": "3.3V–5.5V",
        "search_keys": ["ds18b20", "18b20", "onewire temperatura", "dallas temperature"],
    },

    "hc_sr04": {
        "label": "HC-SR04 (ultrasonido distancia)",
        "pins": {
            "VCC":  "Alimentación 5V — no funciona correctamente con 3.3V",
            "TRIG": "Disparo — salida digital del MCU, pulso HIGH 10µs mínimo",
            "ECHO": "Respuesta — retorna 5V, requiere divisor en MCUs 3.3V",
            "GND":  "Tierra",
        },
        "wiring_notes": [
            "ECHO retorna 5V: en ESP32/Pico usar divisor resistivo 1kΩ(serie) + 2kΩ(a GND) → 3.3V",
            "Timeout pulseIn: usar 30000µs (equivale ~400cm, rango máximo útil)",
            "Alimentar con 5V — con 3.3V el transductor ultrasónico no trabaja",
        ],
        "critical_warnings": [
            "ECHO a 5V directo en GPIO de ESP32/Pico → quema el pin (max entrada 3.3V)",
        ],
        "voltage": "VCC=5V, ECHO pin = 5V lógica",
        "search_keys": ["hc-sr04", "hcsr04", "hc sr04", "ultrasonico", "ultrasonic", "sr04"],
    },

    "bmp280": {
        "label": "BMP280 / BME280 (presión+temperatura I2C)",
        "pins": {
            "VCC": "Alimentación 3.3V (módulo puede tener regulador para 5V)",
            "GND": "Tierra",
            "SCL": "Clock I2C",
            "SDA": "Data I2C",
            "CSB": "Chip Select — HIGH para modo I2C",
            "SDO": "Selección dirección I2C: GND=0x76, VCC=0x77",
        },
        "wiring_notes": [
            "CSB a VCC para modo I2C",
            "SDO a GND → dirección 0x76; SDO a VCC → dirección 0x77",
            "Pull-ups I2C 4.7kΩ en SDA y SCL si no están en el módulo",
        ],
        "critical_warnings": [
            "Dirección I2C depende de SDO — verificar antes de init en firmware",
        ],
        "voltage": "1.8V–3.6V (3.3V recomendado)",
        "search_keys": ["bmp280", "bme280", "bmp 280", "bme 280", "presion barometrica"],
    },

    "mpu6050": {
        "label": "MPU-6050 (acelerómetro+giroscopio I2C)",
        "pins": {
            "VCC": "Alimentación 3.3V–5V",
            "GND": "Tierra",
            "SCL": "Clock I2C",
            "SDA": "Data I2C",
            "AD0": "Dirección I2C: GND=0x68 (defecto), VCC=0x69",
            "INT": "Pin de interrupción (opcional, activo HIGH)",
        },
        "wiring_notes": [
            "Pull-ups I2C 4.7kΩ en SDA y SCL",
            "AD0 a GND para dirección 0x68",
        ],
        "critical_warnings": [],
        "voltage": "3.3V–5V",
        "search_keys": ["mpu6050", "mpu-6050", "mpu 6050", "acelerometro", "giroscopio", "imu"],
    },

    "ina219": {
        "label": "INA219 (medidor corriente/tensión I2C)",
        "pins": {
            "VCC":  "Alimentación 3.3V–5V",
            "GND":  "Tierra",
            "SCL":  "Clock I2C",
            "SDA":  "Data I2C",
            "VIN+": "Terminal positivo del shunt (lado de la fuente)",
            "VIN-": "Terminal negativo del shunt (lado de la carga)",
        },
        "wiring_notes": [
            "El shunt de 0.1Ω va entre VIN+ y VIN- en serie con la carga",
            "Dirección I2C 0x40 (defecto con A0=A1=GND)",
            "Pull-ups I2C 4.7kΩ en SDA y SCL",
        ],
        "critical_warnings": [],
        "voltage": "3.3V–5V",
        "search_keys": ["ina219", "ina 219", "sensor corriente", "corriente i2c", "power monitor"],
    },

    "hx711": {
        "label": "HX711 (ADC para celda de carga)",
        "pins": {
            "VCC": "Alimentación 5V",
            "GND": "Tierra",
            "DT":  "Data — pin digital del MCU",
            "SCK": "Clock — pin digital del MCU (NO es el SCK del SPI estándar)",
            "E+":  "Excitación positiva de la celda de carga",
            "E-":  "Excitación negativa",
            "A+":  "Entrada diferencial A positivo",
            "A-":  "Entrada diferencial A negativo",
        },
        "wiring_notes": [
            "DT y SCK van a GPIO digitales libres — NO son I2C ni SPI estándar",
            "Protocolo propietario: librería HX711 maneja el timing bit a bit",
        ],
        "critical_warnings": [
            "NO conectar DT/SCK a los pines I2C del MCU — el protocolo es incompatible con I2C",
        ],
        "voltage": "5V",
        "search_keys": ["hx711", "hx 711", "celda de carga", "balanza", "load cell", "peso"],
    },

    "fc28": {
        "label": "FC-28 / YL-69 (humedad de suelo analógico)",
        "pins": {
            "VCC": "Alimentación 3.3V–5V",
            "GND": "Tierra",
            "AO":  "Salida analógica (0V=muy húmedo, VCC=muy seco)",
            "DO":  "Salida digital comparador (umbral ajustable con trimpot)",
        },
        "wiring_notes": [
            "AO → pin ADC del MCU para lectura proporcional",
            "En ESP32 con WiFi: usar solo ADC1 (GPIO32–39), nunca ADC2",
        ],
        "critical_warnings": [
            "ESP32 con WiFi activo: ADC2 (GPIO0/2/4/12-15/25-27) no funciona → usar GPIO32-39",
        ],
        "voltage": "3.3V–5V",
        "search_keys": ["fc28", "fc-28", "yl-69", "yl69", "humedad suelo", "soil moisture", "moisture sensor"],
    },

    "pir": {
        "label": "PIR HC-SR501 (detector de movimiento)",
        "pins": {
            "VCC": "Alimentación 5V–12V",
            "OUT": "Salida digital — HIGH cuando detecta movimiento",
            "GND": "Tierra",
        },
        "wiring_notes": [
            "Salida OUT es 3.3V con VCC=5V en la mayoría de módulos — compatible con ESP32/Pico",
            "Tiempo de retención y sensibilidad ajustables con los dos trimpots del módulo",
            "Tiempo de calentamiento al encender: ~30 segundos antes de lecturas válidas",
        ],
        "critical_warnings": [],
        "voltage": "VCC=5V-12V, OUT=3.3V",
        "search_keys": ["pir", "hc-sr501", "sensor movimiento", "detector movimiento", "motion sensor"],
    },

    # ── DRIVERS & ICs ─────────────────────────────────────────────────────────

    "l298n": {
        "label": "L298N (driver motor DC/stepper dual hasta 2A)",
        "pins": {
            "VCC":  "Lógica 5V (del regulador interno del módulo)",
            "GND":  "Tierra común",
            "VS":   "Alimentación motor 7V–35V",
            "IN1":  "Control canal A dirección 1",
            "IN2":  "Control canal A dirección 2",
            "IN3":  "Control canal B dirección 1",
            "IN4":  "Control canal B dirección 2",
            "ENA":  "Enable canal A — jumper=velocidad fija, GPIO PWM=velocidad variable",
            "ENB":  "Enable canal B",
            "OUT1": "Motor A terminal 1",
            "OUT2": "Motor A terminal 2",
            "OUT3": "Motor B terminal 1",
            "OUT4": "Motor B terminal 2",
        },
        "wiring_notes": [
            "IN1=HIGH, IN2=LOW → avance; IN1=LOW, IN2=HIGH → reversa; ambos LOW → freno",
            "ENA/ENB con jumper: velocidad máxima fija. Sin jumper + PWM: velocidad variable",
            "Cap bulk 470µF entre VS y GND para absorber picos de corriente del motor",
            "Módulo incluye diodos flyback en las salidas — no agregar externos",
        ],
        "critical_warnings": [
            "Corriente máxima 2A por canal — motor más grande necesita TB6600 u otro driver",
            "El IC se calienta mucho con corrientes > 1A — agregar disipador",
        ],
        "voltage": "VS=7V-35V, VCC lógica=5V",
        "search_keys": ["l298n", "l298", "driver motor", "puente h", "h-bridge"],
    },

    "drv8825": {
        "label": "DRV8825 (driver paso a paso microstepping)",
        "pins": {
            "VMOT": "Alimentación motor 8.2V–45V",
            "GND":  "Tierra (dos pines: lógica y potencia)",
            "VDD":  "Lógica 3.3V–5V",
            "SLP":  "Sleep activo bajo — HIGH para habilitar (conectar a RST)",
            "RST":  "Reset activo bajo — HIGH para operar (conectar a SLP)",
            "STEP": "Pulso de paso — flanco ascendente = 1 paso",
            "DIR":  "Dirección HIGH=CW, LOW=CCW",
            "EN":   "Enable activo bajo — LOW para habilitar motor",
            "M0/M1/M2": "Microstepping: 000=full,001=1/2,010=1/4,011=1/8,100=1/16,111=1/32",
            "A1/A2": "Bobina A del motor",
            "B1/B2": "Bobina B del motor",
        },
        "wiring_notes": [
            "SLP y RST conectar juntos a VDD para operación normal",
            "Cap electrolítico 100µF entre VMOT y GND — OBLIGATORIO contra picos inductivos",
            "Cap cerámico 100nF entre VMOT y GND junto al electrolítico",
            "Ajustar Vref para limitar corriente ANTES de conectar el motor",
        ],
        "critical_warnings": [
            "NUNCA conectar/desconectar el motor con alimentación activa — destruye el IC",
            "SIN cap 100µF en VMOT: picos EMF del motor destruyen el driver",
        ],
        "voltage": "VMOT=8.2V-45V, VDD=3.3V-5V",
        "search_keys": ["drv8825", "drv 8825", "stepper driver", "driver paso a paso"],
    },

    "a4988": {
        "label": "A4988 (driver paso a paso Pololu)",
        "pins": {
            "VMOT": "Alimentación motor 8V–35V",
            "GND":  "Tierra",
            "VDD":  "Lógica 3.3V–5V",
            "STEP": "Pulso de paso",
            "DIR":  "Dirección",
            "EN":   "Enable activo bajo",
            "RST":  "Reset activo bajo — conectar a SLP",
            "SLP":  "Sleep activo bajo — conectar a RST",
            "MS1/MS2/MS3": "Microstepping: 000=full,001=1/2,010=1/4,011=1/8,111=1/16",
            "1A/1B/2A/2B": "Bobinas del motor",
        },
        "wiring_notes": [
            "RST y SLP conectar juntos a VDD",
            "Cap 100µF entre VMOT y GND — obligatorio",
            "Ajustar corriente por trimpot antes de conectar el motor",
        ],
        "critical_warnings": [
            "NUNCA desconectar el motor con alimentación activa",
            "SIN cap 100µF en VMOT el driver se destruye por picos inductivos",
        ],
        "voltage": "VMOT=8V-35V, VDD=3.3V-5V",
        "search_keys": ["a4988", "a 4988", "pololu stepper"],
    },

    "lm317": {
        "label": "LM317 (regulador lineal ajustable)",
        "pins": {
            "IN":  "Entrada tensión — debe ser Vout + 3V mínimo",
            "OUT": "Salida tensión regulada",
            "ADJ": "Ajuste — divisor R1 (240Ω entre OUT y ADJ) y R2 (entre ADJ y GND)",
        },
        "wiring_notes": [
            "Vout = 1.25V × (1 + R2/R1); con R1=240Ω → R2 = (Vout/1.25 - 1) × 240",
            "Cap 0.1µF cerámico en IN, cap 1µF electrolítico en OUT",
            "Carga mínima 10mA — agregar R de carga si necesario",
        ],
        "critical_warnings": [
            "Dropout ~3V: Vin debe ser al menos Vout + 3V",
        ],
        "voltage": "Vin max 40V, Vout ajustable 1.25V–37V",
        "search_keys": ["lm317", "lm 317", "regulador ajustable", "regulador lineal variable"],
    },

    "lm7805": {
        "label": "LM7805 (regulador 5V fijo)",
        "pins": {
            "IN":  "Entrada 7V–35V",
            "GND": "Tierra (pin central)",
            "OUT": "Salida 5V regulada",
        },
        "wiring_notes": [
            "Cap 0.33µF cerámico en IN, cap 0.1µF cerámico en OUT",
            "Con carga > 200mA: disipador térmico obligatorio",
        ],
        "critical_warnings": [
            "Dropout ~2V: Vin mínimo 7V para 5V estable",
            "Sin disipador se apaga por temperatura con corriente > 300mA",
        ],
        "voltage": "Vin=7V-35V, Vout=5V",
        "search_keys": ["lm7805", "7805", "lm 7805", "regulador 5v fijo"],
    },

    "ams1117": {
        "label": "AMS1117 (regulador LDO 3.3V o 5V)",
        "pins": {
            "GND": "Tierra",
            "OUT": "Salida regulada (3.3V o 5V según versión)",
            "IN":  "Entrada tensión",
        },
        "wiring_notes": [
            "Cap 10µF electrolítico en IN y OUT para estabilidad",
            "Dropout muy bajo (~1.2V) — ideal para baterías LiPo",
        ],
        "critical_warnings": [],
        "voltage": "Vin max 15V, Vout=3.3V o 5V, Imax=1A",
        "search_keys": ["ams1117", "ams 1117", "ldo 3.3v", "regulador ldo", "1117"],
    },

    "ne555": {
        "label": "NE555 (temporizador)",
        "pins": {
            "1_GND":  "Tierra",
            "2_TRIG": "Disparo activo bajo (dispara cuando baja < Vcc/3)",
            "3_OUT":  "Salida (0V o cerca de Vcc)",
            "4_RST":  "Reset activo bajo — conectar a Vcc para operación normal",
            "5_CV":   "Control voltaje — cap 10nF a GND para filtrar ruido",
            "6_THR":  "Umbral (resetea timer cuando sube > 2×Vcc/3)",
            "7_DIS":  "Descarga capacitor de temporización",
            "8_VCC":  "Alimentación 5V–15V",
        },
        "wiring_notes": [
            "Modo astable: R1 entre VCC-DIS, R2 entre DIS-TRIG/THR, C entre TRIG/THR-GND; f=1.44/((R1+2R2)×C)",
            "Modo monoestable: C entre THR-GND, R entre VCC-THR; t=1.1×R×C",
            "Pin4 RST a VCC si no se usa; pin5 CV cap 10nF a GND",
        ],
        "critical_warnings": [],
        "voltage": "5V–15V (CMOS 555: 3V–15V)",
        "search_keys": ["ne555", "555", "temporizador", "timer 555", "oscilador 555"],
    },

    # ── RTC ───────────────────────────────────────────────────────────────────

    "ds3231": {
        "label": "DS3231 (RTC alta precisión I2C)",
        "pins": {
            "VCC": "Alimentación 3.3V–5.5V",
            "GND": "Tierra",
            "SCL": "Clock I2C",
            "SDA": "Data I2C",
            "SQW": "Onda cuadrada/interrupción (open-drain, pull-up 10kΩ si se usa)",
            "32K": "Salida 32kHz (open-drain)",
        },
        "wiring_notes": [
            "Pull-ups I2C 4.7kΩ en SDA y SCL",
            "Dirección I2C fija 0x68 (no configurable)",
            "El módulo incluye batería CR2032 para respaldo de hora",
        ],
        "critical_warnings": [
            "Sin batería CR2032 el RTC pierde la hora al quitar la alimentación principal",
        ],
        "voltage": "3.3V–5.5V",
        "search_keys": ["ds3231", "ds 3231", "rtc", "reloj tiempo real", "real time clock", "ds1307"],
    },

    # ── DISPLAYS ──────────────────────────────────────────────────────────────

    "oled_ssd1306": {
        "label": "OLED SSD1306 128×64 I2C",
        "pins": {
            "VCC": "Alimentación 3.3V–5V",
            "GND": "Tierra",
            "SCL": "Clock I2C",
            "SDA": "Data I2C",
        },
        "wiring_notes": [
            "Pull-ups I2C 4.7kΩ en SDA y SCL (la mayoría de módulos los incluyen)",
            "Dirección I2C: 0x3C (defecto) o 0x3D según jumper SA0",
        ],
        "critical_warnings": [],
        "voltage": "3.3V–5V",
        "search_keys": ["oled", "ssd1306", "oled 128x64", "oled i2c", "pantalla oled"],
    },

    "lcd_i2c": {
        "label": "LCD I2C 16×2 (backpack PCF8574)",
        "pins": {
            "VCC": "Alimentación 5V",
            "GND": "Tierra",
            "SCL": "Clock I2C",
            "SDA": "Data I2C",
        },
        "wiring_notes": [
            "Alimentar con 5V — con 3.3V el backlight no enciende",
            "Dirección I2C: 0x27 (PCF8574) o 0x3F (PCF8574A) — verificar con I2C scanner",
            "El trimpot azul del módulo ajusta el contraste",
        ],
        "critical_warnings": [
            "Con 3.3V el backlight no enciende y el contraste puede ser insuficiente",
        ],
        "voltage": "5V",
        "search_keys": ["lcd", "lcd i2c", "lcd 16x2", "pantalla lcd", "liquidcrystal i2c"],
    },

    # ── COMUNICACIONES ────────────────────────────────────────────────────────

    "hc05": {
        "label": "HC-05 (Bluetooth Serial)",
        "pins": {
            "VCC":   "Alimentación 5V",
            "GND":   "Tierra",
            "TXD":   "TX del módulo → RX del MCU (3.3V lógica)",
            "RXD":   "RX del módulo → TX del MCU — MÁXIMO 3.3V",
            "KEY":   "Modo AT: HIGH con módulo encendido para entrar a comandos AT",
            "STATE": "HIGH cuando está pareado/conectado",
        },
        "wiring_notes": [
            "RXD del HC-05 acepta máximo 3.3V — con Arduino 5V usar divisor 1kΩ+2kΩ en TX del Arduino",
            "Baudrate defecto: 9600 bps datos, 38400 bps modo AT",
        ],
        "critical_warnings": [
            "RXD del módulo tolera solo 3.3V — 5V puede dañar el módulo",
        ],
        "voltage": "VCC=5V, lógica UART=3.3V",
        "search_keys": ["hc-05", "hc05", "hc 05", "bluetooth serial", "bt serial"],
    },

    "nrf24l01": {
        "label": "nRF24L01+ (transceiver 2.4GHz SPI)",
        "pins": {
            "VCC":  "Alimentación 1.9V–3.6V — NO 5V",
            "GND":  "Tierra",
            "CE":   "Chip Enable — control RX/TX (GPIO libre del MCU)",
            "CSN":  "Chip Select SPI activo bajo (GPIO libre del MCU)",
            "SCK":  "Clock SPI",
            "MOSI": "Master Out Slave In",
            "MISO": "Master In Slave Out",
            "IRQ":  "Interrupción activo bajo (opcional)",
        },
        "wiring_notes": [
            "Cap 10µF electrolítico + 100nF cerámico entre VCC y GND junto al módulo — obligatorio",
            "Con Arduino 5V: level shifter en CE, CSN, SCK, MOSI (o módulo con adaptador 3.3V incluido)",
            "CE y CSN son pines arbitrarios del MCU, no los SPI hardware obligatoriamente",
        ],
        "critical_warnings": [
            "VCC máximo 3.6V — 5V destruye el módulo de inmediato",
            "SIN caps de desacople junto al VCC: el módulo se reinicia al transmitir por pico de corriente",
        ],
        "voltage": "1.9V–3.6V",
        "search_keys": ["nrf24l01", "nrf24", "2.4ghz transceiver", "nordic", "nrf"],
    },

    # ── MÓDULOS ───────────────────────────────────────────────────────────────

    "relay_module": {
        "label": "Módulo Relay 5V (1-4 canales con optoacoplador)",
        "pins": {
            "VCC": "Alimentación 5V",
            "GND": "Tierra",
            "IN":  "Señal de control del MCU — ACTIVO LOW (LOW=relay ON, HIGH=relay OFF)",
            "COM": "Terminal común del contacto",
            "NO":  "Normalmente Abierto (conecta con COM al activar)",
            "NC":  "Normalmente Cerrado (conecta con COM al desactivar)",
        },
        "wiring_notes": [
            "En setup(): pinMode(RELAY_PIN, OUTPUT); digitalWrite(RELAY_PIN, HIGH); // inactivo al arrancar",
            "Activar: digitalWrite(RELAY_PIN, LOW); Desactivar: digitalWrite(RELAY_PIN, HIGH)",
            "El módulo incluye diodo flyback — no agregar externo",
            "Carga conectar entre COM y NO (o NC según lógica deseada)",
        ],
        "critical_warnings": [
            "NUNCA mezclar la tierra de la carga AC con la tierra del circuito de control",
        ],
        "voltage": "VCC=5V, carga hasta 10A/250VAC",
        "search_keys": ["relay module", "relay", "rele", "modulo relay", "módulo relé", "relé"],
    },

    "servo": {
        "label": "Servo Motor (SG90/MG996R y similares)",
        "pins": {
            "VCC":    "Alimentación 5V (SG90: 100–250mA, MG996R: hasta 1A en movimiento)",
            "GND":    "Tierra",
            "SIGNAL": "PWM de control — 50Hz, pulso 1ms–2ms → 0°–180°",
        },
        "wiring_notes": [
            "Pin SIGNAL al pin PWM del MCU (cualquier GPIO en ESP32, D3/5/6/9/10/11 en Arduino Uno)",
            "Alimentar VCC desde fuente independiente si el servo es grande (>SG90) para no sobrecargar el MCU",
            "Cap 100µF entre VCC y GND del servo para absorber picos de corriente",
        ],
        "critical_warnings": [
            "MG996R consume hasta 1A en arranque — el regulador del Arduino no puede darlo",
        ],
        "voltage": "5V (algunos 6V)",
        "search_keys": ["servo", "servo motor", "sg90", "mg996r", "motor servo"],
    },

    "neopixel": {
        "label": "NeoPixel WS2812B (LED RGB direccionable)",
        "pins": {
            "VCC":  "Alimentación 5V (cada LED consume hasta 60mA a máx brillo)",
            "GND":  "Tierra",
            "DATA": "Señal de control unidireccional — resistencia 300–500Ω en serie",
        },
        "wiring_notes": [
            "Resistencia 300–500Ω en la línea DATA entre MCU y primer LED",
            "Cap 1000µF entre VCC y GND al inicio de la tira para picos de corriente",
            "Alimentar tiras largas también desde el final para evitar caída de tensión",
            "Calcular fuente: N LEDs × 60mA = corriente máxima total",
        ],
        "critical_warnings": [
            "SIN resistencia en DATA: picos de EMI pueden corromper la señal o dañar el primer LED",
        ],
        "voltage": "5V",
        "search_keys": ["neopixel", "ws2812", "ws2812b", "led rgb", "led direccionable", "rgb strip"],
    },
}

# ────────────────────────────────────────────────────────────────────────────
# LOOKUP: all search_keys → PINOUTS key
# ────────────────────────────────────────────────────────────────────────────

_LOOKUP: dict[str, str] = {}
for _pkey, _pdata in PINOUTS.items():
    _LOOKUP[_pkey.lower()] = _pkey
    for _skey in _pdata.get("search_keys", []):
        _LOOKUP[_skey.lower()] = _pkey


def get_component_pinout(name: str) -> Optional[dict]:
    """Return pinout entry for a component by name (fuzzy match)."""
    nl = name.lower().strip()
    if nl in _LOOKUP:
        return PINOUTS[_LOOKUP[nl]]
    for skey, pkey in _LOOKUP.items():
        if skey in nl or nl in skey:
            return PINOUTS[pkey]
    return None


def get_pinout_context_for_prompt(descriptions: list[str]) -> str:
    """
    Scan descriptions for known component names and return a formatted block
    of verified pinout data to inject into the circuit-generation LLM prompt.

    Args:
        descriptions: list of strings (circuit description, component names, etc.)
    Returns:
        Formatted string with pinouts, or "" if no known components found.
    """
    found: dict[str, dict] = {}

    combined = " ".join(d.lower() for d in descriptions if d)
    for skey, pkey in _LOOKUP.items():
        if skey in combined and pkey not in found:
            found[pkey] = PINOUTS[pkey]

    if not found:
        return ""

    lines = ["PINOUTS VERIFICADOS — usá estos datos exactos en la netlist:"]
    for pdata in found.values():
        lines.append(f"\n▶ {pdata['label']} ({pdata['voltage']})")
        for pin_name, pin_desc in pdata["pins"].items():
            lines.append(f"   {pin_name}: {pin_desc}")
        for note in pdata["wiring_notes"][:2]:
            lines.append(f"   → {note}")
        for warn in pdata["critical_warnings"]:
            lines.append(f"   ⚠ CRÍTICO: {warn}")

    return "\n".join(lines)
