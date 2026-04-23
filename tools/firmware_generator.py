# tools/firmware_generator.py
#
# Genera código de firmware según la plataforma del dispositivo.
# Usa el LLM para generar código específico y correcto.

import os
import httpx
from pathlib import Path
from core.config import LLM_API, LLM_MODEL_SMART as LLM_MODEL, get_llm_headers
from core.logger import logger

FIRMWARE_DIR = os.path.abspath("./agent_files/firmware")

PLATFORM_PROMPTS = {
    "arduino:avr": """Eres un experto en programación de Arduino (C++).
Generá código Arduino C++ válido, robusto y completo para el siguiente requerimiento.
Reglas obligatorias:
- Solo código C++ válido para Arduino (AVR)
- Siempre incluí setup() y loop()
- MANEJO DE ERRORES: en lecturas de sensores usá rangos de validación y valor de fallback si el sensor falla
- ESTADO SERIAL: al final de loop() emitir una línea: Serial.println("STATE:" + estadoJSON) donde estadoJSON es un JSON con los valores clave (pines activos, lecturas, estados de actuadores)
  Ejemplo: STATE:{"D13":1,"A0":512,"relay":0}
- WATCHDOG: incluí #include <avr/wdt.h> y wdt_enable(WDTO_8S) en setup(); wdt_reset() en loop()
- Usá las librerías estándar de Arduino
- No incluyas explicaciones fuera del código
- Devolvé SOLO el código, sin markdown ni backticks""",

    "esp32:esp32": """Eres un experto en programación de ESP32 con Arduino framework.
Generá código C++ válido, robusto y production-ready para ESP32.
Reglas obligatorias:
- Código C++ válido para ESP32 con Arduino framework
- Siempre incluí setup() y loop()
- OTA UPDATE: incluí soporte ArduinoOTA básico en setup() y handle en loop() cuando la plataforma lo permite (si hay WiFi en el circuito, siempre incluirlo)
  ```cpp
  #include <ArduinoOTA.h>
  // En setup(): ArduinoOTA.begin();
  // En loop(): ArduinoOTA.handle();
  ```
- WATCHDOG: incluí esp_task_wdt_init(10, true) y esp_task_wdt_add(NULL) en setup(); esp_task_wdt_reset() en loop()
- MANEJO DE ERRORES: try/catch no existe en C++, usá validación de rangos y retry en inicializaciones de sensores I2C con Wire.begin()
- ESTADO SERIAL: al final de loop() emitir: Serial.println("STATE:" + estadoJSON) con JSON de valores clave
  Ejemplo: STATE:{"GPIO2":1,"ADC1":2048,"temp":23.5,"relay":0}
- Incluí WiFi.h, ArduinoOTA.h cuando haya WiFi
- No incluyas explicaciones fuera del código
- Devolvé SOLO el código, sin markdown ni backticks""",

    "esp8266:esp8266": """Eres un experto en programación de ESP8266 con Arduino framework.
Generá código C++ válido, robusto y completo para ESP8266.
Reglas obligatorias:
- Código C++ válido para ESP8266
- Siempre incluí setup() y loop()
- OTA UPDATE: incluí ArduinoOTA básico cuando hay WiFi en el circuito
- WATCHDOG: usá ESP.wdtEnable(8000) en setup() y ESP.wdtFeed() en loop()
- ESTADO SERIAL: al final de loop() emitir: Serial.println("STATE:" + estadoJSON) con JSON de valores clave
- Usá ESP8266WiFi.h para WiFi
- No incluyas explicaciones fuera del código
- Devolvé SOLO el código, sin markdown ni backticks""",

    "micropython": """Eres un experto en MicroPython para microcontroladores.
Generá código MicroPython válido, robusto y completo.
Reglas obligatorias:
- Solo código MicroPython válido
- Estructura main con try/except global para capturar errores y resetear si necesario
- MANEJO DE ERRORES: try/except en lecturas de sensores, logging de errores por UART
- WATCHDOG: usá machine.WDT(timeout=8000) y wdt.feed() en el loop principal
- ESTADO SERIAL: en el loop principal imprimir: print("STATE:" + json.dumps(estado)) con dict de valores clave
  Ejemplo: STATE:{"pin2":1,"adc":512,"temp":23.5}
- Usá las librerías estándar de MicroPython (machine, utime, ujson, etc.)
- No incluyas explicaciones fuera del código
- Devolvé SOLO el código, sin markdown ni backticks""",
}

DEFAULT_PROMPT = """Eres un experto en programación de microcontroladores.
Generá código de firmware válido para el siguiente requerimiento.
Devolvé SOLO el código, sin explicaciones ni markdown."""


# ──────────────────────────────────────────────────────────────────────────────
# Component snippet library — pre-validated patterns injected into the prompt
# to prevent the most common compile errors and library mismatches.
# ──────────────────────────────────────────────────────────────────────────────

COMPONENT_SNIPPETS: dict[str, dict] = {
    "dht22": {
        "includes": ["#include <DHT.h>"],
        "lib": "DHT sensor library",
        "snippet": (
            "// DHT22 — temperatura y humedad\n"
            "// arduino-cli lib install \"DHT sensor library\"\n"
            "DHT dht(DHT_PIN, DHT22);\n"
            "// setup(): dht.begin();\n"
            "// loop():  float t = dht.readTemperature();\n"
            "//          float h = dht.readHumidity();\n"
            "//          if (isnan(t) || isnan(h)) { /* error lectura */ }"
        ),
    },
    "dht11": {
        "includes": ["#include <DHT.h>"],
        "lib": "DHT sensor library",
        "snippet": (
            "// DHT11 — temperatura y humedad\n"
            "DHT dht(DHT_PIN, DHT11);\n"
            "// setup(): dht.begin();\n"
            "// loop():  float t = dht.readTemperature(); float h = dht.readHumidity();"
        ),
    },
    "ds18b20": {
        "includes": ["#include <OneWire.h>", "#include <DallasTemperature.h>"],
        "lib": "DallasTemperature",
        "snippet": (
            "// DS18B20 — temperatura One-Wire\n"
            "// arduino-cli lib install \"DallasTemperature\"\n"
            "OneWire oneWire(ONE_WIRE_BUS);\n"
            "DallasTemperature sensors(&oneWire);\n"
            "// setup(): sensors.begin();\n"
            "// loop():  sensors.requestTemperatures();\n"
            "//          float t = sensors.getTempCByIndex(0);\n"
            "//          if (t == DEVICE_DISCONNECTED_C) { /* error */ }"
        ),
    },
    "hc_sr04": {
        "includes": [],
        "lib": "",
        "snippet": (
            "// HC-SR04 — distancia ultrasónica\n"
            "// ECHO necesita divisor 1kΩ/2kΩ en MCUs de 3.3V\n"
            "// loop():\n"
            "//   digitalWrite(TRIG_PIN, LOW); delayMicroseconds(2);\n"
            "//   digitalWrite(TRIG_PIN, HIGH); delayMicroseconds(10);\n"
            "//   digitalWrite(TRIG_PIN, LOW);\n"
            "//   long dur = pulseIn(ECHO_PIN, HIGH, 30000UL); // 30ms timeout\n"
            "//   float dist_cm = (dur == 0) ? -1 : dur * 0.034f / 2.0f;"
        ),
    },
    "bmp280": {
        "includes": ["#include <Wire.h>", "#include <Adafruit_BMP280.h>"],
        "lib": "Adafruit BMP280 Library",
        "snippet": (
            "// BMP280 — presión y temperatura I2C (0x76 o 0x77)\n"
            "// arduino-cli lib install \"Adafruit BMP280 Library\"\n"
            "Adafruit_BMP280 bmp;\n"
            "// setup(): Wire.begin(); if (!bmp.begin(0x76)) { /* error I2C */ }\n"
            "// loop():  float t = bmp.readTemperature();\n"
            "//          float p = bmp.readPressure() / 100.0F; // hPa"
        ),
    },
    "mpu6050": {
        "includes": ["#include <Wire.h>", "#include <MPU6050.h>"],
        "lib": "MPU6050",
        "snippet": (
            "// MPU-6050 — acelerómetro + giroscopio I2C\n"
            "// arduino-cli lib install \"MPU6050\"\n"
            "MPU6050 mpu;\n"
            "// setup(): Wire.begin(); mpu.initialize();\n"
            "//          if (!mpu.testConnection()) { /* error */ }\n"
            "// loop():  int16_t ax,ay,az,gx,gy,gz;\n"
            "//          mpu.getMotion6(&ax,&ay,&az,&gx,&gy,&gz);"
        ),
    },
    "relay_module": {
        "includes": [],
        "lib": "",
        "snippet": (
            "// Relay — módulo active-LOW (LOW = activado)\n"
            "// setup(): pinMode(RELAY_PIN, OUTPUT); digitalWrite(RELAY_PIN, HIGH);\n"
            "// Activar:   digitalWrite(RELAY_PIN, LOW);\n"
            "// Desactivar: digitalWrite(RELAY_PIN, HIGH);"
        ),
    },
    "relay": {
        "includes": [],
        "lib": "",
        "snippet": (
            "// Relay — active-LOW con diodo flyback 1N4007 en bobina\n"
            "// setup(): pinMode(RELAY_PIN, OUTPUT); digitalWrite(RELAY_PIN, HIGH);\n"
            "// ON: digitalWrite(RELAY_PIN, LOW);  OFF: digitalWrite(RELAY_PIN, HIGH);"
        ),
    },
    "servo": {
        "includes": ["#include <Servo.h>"],
        "lib": "",
        "snippet": (
            "// Servo motor (librería incluida en Arduino)\n"
            "Servo myServo;\n"
            "// setup(): myServo.attach(SERVO_PIN);\n"
            "// loop():  myServo.write(90); // 0-180 grados"
        ),
    },
    "oled": {
        "includes": ["#include <Wire.h>", "#include <Adafruit_GFX.h>",
                     "#include <Adafruit_SSD1306.h>"],
        "lib": "Adafruit SSD1306",
        "snippet": (
            "// OLED SSD1306 I2C 128x64\n"
            "// arduino-cli lib install \"Adafruit SSD1306\"\n"
            "#define SCREEN_WIDTH 128\n"
            "#define SCREEN_HEIGHT 64\n"
            "Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);\n"
            "// setup(): display.begin(SSD1306_SWITCHCAPVCC, 0x3C);\n"
            "//          display.clearDisplay(); display.display();\n"
            "// Uso: display.setTextSize(1); display.setTextColor(WHITE);\n"
            "//      display.setCursor(0,0); display.println(\"Hola\"); display.display();"
        ),
    },
    "lcd": {
        "includes": ["#include <LiquidCrystal_I2C.h>"],
        "lib": "LiquidCrystal I2C",
        "snippet": (
            "// LCD I2C 16x2 (backpack PCF8574)\n"
            "// arduino-cli lib install \"LiquidCrystal I2C\"\n"
            "LiquidCrystal_I2C lcd(0x27, 16, 2);\n"
            "// setup(): lcd.init(); lcd.backlight();\n"
            "// Uso: lcd.setCursor(0,0); lcd.print(\"Hola\");"
        ),
    },
    "rtc": {
        "includes": ["#include <Wire.h>", "#include <RTClib.h>"],
        "lib": "RTClib",
        "snippet": (
            "// RTC DS3231 I2C\n"
            "// arduino-cli lib install \"RTClib\"\n"
            "RTC_DS3231 rtc;\n"
            "// setup(): rtc.begin();\n"
            "// loop():  DateTime now = rtc.now();\n"
            "//          int h = now.hour(); int m = now.minute(); int s = now.second();"
        ),
    },
    "ds3231": {
        "includes": ["#include <Wire.h>", "#include <RTClib.h>"],
        "lib": "RTClib",
        "snippet": (
            "// DS3231 RTC I2C\n"
            "// arduino-cli lib install \"RTClib\"\n"
            "RTC_DS3231 rtc;\n"
            "// setup(): rtc.begin();\n"
            "//          // Para sincronizar: rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));\n"
            "// loop():  DateTime now = rtc.now();\n"
            "//          char buf[20]; sprintf(buf, \"%02d:%02d:%02d\", now.hour(), now.minute(), now.second());"
        ),
    },
    "moisture_sensor": {
        "includes": [],
        "lib": "",
        "snippet": (
            "// Sensor humedad suelo FC-28 / YL-69 — pin analógico\n"
            "// Valores: 0 = muy húmedo, 1023 (AVR) / 4095 (ESP32) = muy seco\n"
            "// loop(): int raw = analogRead(MOISTURE_PIN);\n"
            "//         int pct = map(raw, 0, 1023, 100, 0); // 100%=húmedo 0%=seco\n"
            "//         if (pct < 30) { /* activar riego */ }"
        ),
    },
    "pir": {
        "includes": [],
        "lib": "",
        "snippet": (
            "// PIR HC-SR501 — HIGH = movimiento detectado\n"
            "// setup(): pinMode(PIR_PIN, INPUT);\n"
            "// loop():  if (digitalRead(PIR_PIN) == HIGH) { /* movimiento */ }"
        ),
    },
    "l298n": {
        "includes": [],
        "lib": "",
        "snippet": (
            "// L298N — driver motor DC dual\n"
            "// setup(): pinMode(IN1,OUTPUT); pinMode(IN2,OUTPUT); pinMode(ENA,OUTPUT);\n"
            "// Adelante: digitalWrite(IN1,HIGH); digitalWrite(IN2,LOW); analogWrite(ENA,200);\n"
            "// Atrás:    digitalWrite(IN1,LOW);  digitalWrite(IN2,HIGH); analogWrite(ENA,200);\n"
            "// Freno:    digitalWrite(IN1,LOW);  digitalWrite(IN2,LOW);  analogWrite(ENA,0);"
        ),
    },
    "drv8825": {
        "includes": [],
        "lib": "",
        "snippet": (
            "// DRV8825 / A4988 — motor paso a paso\n"
            "// setup(): pinMode(STEP_PIN,OUTPUT); pinMode(DIR_PIN,OUTPUT);\n"
            "//          pinMode(EN_PIN,OUTPUT); digitalWrite(EN_PIN,LOW); // habilitar\n"
            "// Un paso: digitalWrite(DIR_PIN,HIGH); // CW o LOW para CCW\n"
            "//          digitalWrite(STEP_PIN,HIGH); delayMicroseconds(500);\n"
            "//          digitalWrite(STEP_PIN,LOW);  delayMicroseconds(500);"
        ),
    },
    "a4988": {
        "includes": [],
        "lib": "",
        "snippet": (
            "// A4988 — motor paso a paso (igual que DRV8825)\n"
            "// setup(): pinMode(STEP_PIN,OUTPUT); pinMode(DIR_PIN,OUTPUT);\n"
            "//          pinMode(EN_PIN,OUTPUT); digitalWrite(EN_PIN,LOW);\n"
            "// Un paso: digitalWrite(STEP_PIN,HIGH); delayMicroseconds(500);\n"
            "//          digitalWrite(STEP_PIN,LOW);  delayMicroseconds(500);"
        ),
    },
    "neopixel": {
        "includes": ["#include <Adafruit_NeoPixel.h>"],
        "lib": "Adafruit NeoPixel",
        "snippet": (
            "// NeoPixel WS2812B\n"
            "// arduino-cli lib install \"Adafruit NeoPixel\"\n"
            "Adafruit_NeoPixel strip(NUM_LEDS, LED_PIN, NEO_GRB + NEO_KHZ800);\n"
            "// setup(): strip.begin(); strip.setBrightness(50); strip.show();\n"
            "// Uso: strip.setPixelColor(0, strip.Color(255,0,0)); strip.show();"
        ),
    },
    "hx711": {
        "includes": ["#include <HX711.h>"],
        "lib": "HX711 Arduino Library",
        "snippet": (
            "// HX711 — celda de carga\n"
            "// arduino-cli lib install \"HX711 Arduino Library\"\n"
            "HX711 scale;\n"
            "// setup(): scale.begin(DOUT_PIN, SCK_PIN);\n"
            "//          scale.set_scale(CALIBRATION_FACTOR); scale.tare();\n"
            "// loop():  float kg = scale.get_units(5); // promedio 5 lecturas"
        ),
    },
    "fc28": {
        "includes": [],
        "lib": "",
        "snippet": (
            "// FC-28 — sensor humedad analógico\n"
            "// loop(): int val = analogRead(FC28_PIN);\n"
            "//         bool needs_water = (val > 700); // ajustar umbral"
        ),
    },
}

# Aliases para tipos de componente → clave del snippet
_SNIPPET_ALIASES: dict[str, str] = {
    "relay":           "relay",
    "relay_module":    "relay_module",
    "hc_sr04":         "hc_sr04",
    "ultrasonic":      "hc_sr04",
    "ultrasonic_sensor": "hc_sr04",
    "dht22":           "dht22",
    "dht11":           "dht11",
    "ds18b20":         "ds18b20",
    "ds18b20_sensor":  "ds18b20",
    "bmp280":          "bmp280",
    "bme280":          "bmp280",
    "mpu6050":         "mpu6050",
    "servo":           "servo",
    "oled":            "oled",
    "oled_128x64":     "oled",
    "oled_display":    "oled",
    "lcd":             "lcd",
    "i2c_lcd":         "lcd",
    "rtc":             "rtc",
    "rtc_ds3231":      "ds3231",
    "ds3231":          "ds3231",
    "moisture_sensor": "moisture_sensor",
    "soil_moisture":   "moisture_sensor",
    "pir":             "pir",
    "l298n":           "l298n",
    "motor_driver":    "l298n",
    "drv8825":         "drv8825",
    "a4988":           "a4988",
    "stepper_driver":  "drv8825",
    "neopixel":        "neopixel",
    "ws2812":          "neopixel",
    "ws2812b":         "neopixel",
    "hx711":           "hx711",
    "fc28":            "fc28",
    "fc_28":           "fc28",
}


def get_firmware_snippets(components: list) -> str:
    """
    Given a component list from a circuit, returns a block of pre-validated
    code snippets and library hints to inject into the firmware generation prompt.
    """
    seen_keys:     list[str] = []
    seen_includes: list[str] = []
    seen_libs:     list[str] = []
    seen_snippets: list[str] = []

    for comp in (components or []):
        ctype = (comp.get("resolved_type") or comp.get("type") or "").lower().strip()
        cname = (comp.get("name") or "").lower()

        key = _SNIPPET_ALIASES.get(ctype)
        if not key:
            for alias, mapped in _SNIPPET_ALIASES.items():
                if alias in ctype or alias in cname:
                    key = mapped
                    break

        if not key or key in seen_keys:
            continue
        seen_keys.append(key)

        data = COMPONENT_SNIPPETS.get(key)
        if not data:
            continue

        for inc in data["includes"]:
            if inc not in seen_includes:
                seen_includes.append(inc)
        if data["lib"] and data["lib"] not in seen_libs:
            seen_libs.append(data["lib"])
        if data["snippet"] not in seen_snippets:
            seen_snippets.append(data["snippet"])

    if not seen_snippets:
        return ""

    parts: list[str] = []
    if seen_includes:
        parts.append("// INCLUDES REQUERIDOS:\n" + "\n".join(seen_includes))
    if seen_libs:
        lib_lines = "\n".join(f'//   arduino-cli lib install "{lib}"' for lib in seen_libs)
        parts.append("// LIBRERÍAS A INSTALAR:\n" + lib_lines)
    parts.append("// PATRONES DE USO VALIDADOS (usá exactamente estas APIs):")
    parts.extend(seen_snippets)
    return "\n\n".join(parts)


def generate_firmware(
    description:   str,
    platform:      str,
    device_name:   str       = "",
    past_errors:   list[str] = None,
    compile_error: str       = "",
    components:    list      = None,
) -> dict:
    """
    Genera código de firmware usando el LLM.

    Args:
        past_errors:   Errores históricos de compilación para este device (de firmware_history).
        compile_error: Error del intento actual (usado en reintentos).

    Returns:
        { "code", "filename", "platform", "path", "dir" }
    """
    system_prompt = PLATFORM_PROMPTS.get(platform, DEFAULT_PROMPT)

    # Inject component-specific snippets to prevent common compile errors
    if components:
        snippets = get_firmware_snippets(components)
        if snippets:
            system_prompt += (
                "\n\n--- SNIPPETS VALIDADOS PARA LOS COMPONENTES DEL CIRCUITO ---\n"
                + snippets
                + "\n--- FIN SNIPPETS ---\n"
                "Usá exactamente las APIs de los snippets de arriba para los componentes listados."
            )

    user_message = f"Dispositivo: {device_name}\nRequerimiento: {description}"

    # Inyectar errores históricos como contexto preventivo
    if past_errors:
        errors_ctx = "\n".join(f"- {e[:300]}" for e in past_errors[:3])
        user_message += f"\n\nERRORES PREVIOS A EVITAR (este device falló antes con):\n{errors_ctx}"

    # Inyectar error del intento actual (reintento)
    if compile_error:
        user_message += f"\n\nERROR DE COMPILACIÓN DEL INTENTO ANTERIOR:\n{compile_error[:500]}\nCorregí el código para resolver este error específico."

    try:
        response = httpx.post(
            LLM_API,
            headers=get_llm_headers(
                agent_id="hardware-agent",
                agent_name="HardwareAgent"
            ),
            json={
                "model":       LLM_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_message},
                ],
                "temperature": 0.2,
            },
            timeout=180
        )
        response.raise_for_status()
        code = response.json()["choices"][0]["message"]["content"].strip()

        # Limpiar markdown si el modelo lo incluye igual
        code = _clean_code(code)

        # Determinar extensión
        ext      = "ino" if "arduino" in platform or "esp" in platform else "py"
        filename = f"firmware_{device_name.lower().replace(' ', '_')}.{ext}"

        # Guardar en disco
        os.makedirs(FIRMWARE_DIR, exist_ok=True)
        path = os.path.join(FIRMWARE_DIR, filename)

        # Arduino-cli requiere que el .ino esté en una carpeta con el mismo nombre
        if ext == "ino":
            sketch_dir = os.path.join(FIRMWARE_DIR, filename.replace(".ino", ""))
            os.makedirs(sketch_dir, exist_ok=True)
            path = os.path.join(sketch_dir, filename)

        with open(path, "w", encoding="utf-8") as f:
            f.write(code)

        logger.info(f"[Hardware] Firmware generado: {filename}")
        return {
            "code":     code,
            "filename": filename,
            "platform": platform,
            "path":     path,
            "dir":      os.path.dirname(path),
        }

    except Exception as e:
        logger.error(f"[Hardware] Error generando firmware: {e}")
        return {"error": str(e)}


def _clean_code(code: str) -> str:
    """Elimina backticks y markers de markdown del código."""
    lines = code.split("\n")
    clean = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            continue
        clean.append(line)
    return "\n".join(clean).strip()

CIRCUIT_PROMPT = """Eres un experto en programación de microcontroladores con conocimiento específico del circuito.
Genera código de firmware C++ válido para Arduino/ESP32 que implemente exactamente el circuito descrito.
Reglas estrictas:
- Usa SOLO los pines y componentes especificados en el circuito
- Incluye setup() y loop() con la lógica correcta para los componentes
- Comenta el código indicando qué hace cada parte
- No uses pines que no estén en el circuito
- Si hay sensores, lee sus valores correctamente
- Si hay actuadores, controla según el diseño
- Devuelve SOLO el código C++, sin explicaciones ni markdown"""


def generate_firmware_for_circuit(
    circuit_description: str,
    platform:            str,
    device_name:         str       = "",
    past_errors:         list[str] = None,
    compile_error:       str       = "",
    components:          list      = None,
) -> dict:
    """
    Genera firmware específico para un circuito dado.
    Reutiliza la lógica de generate_firmware() con un prompt orientado a circuitos.
    """
    system_prompt = CIRCUIT_PROMPT
    if components:
        snippets = get_firmware_snippets(components)
        if snippets:
            system_prompt += (
                "\n\n--- SNIPPETS VALIDADOS PARA LOS COMPONENTES DEL CIRCUITO ---\n"
                + snippets
                + "\n--- FIN SNIPPETS ---\n"
                "Usá exactamente estas APIs para los componentes del circuito."
            )

    user_message = f"""CIRCUITO A IMPLEMENTAR:
{circuit_description}

DISPOSITIVO: {device_name}
PLATAFORMA: {platform}

Genera el firmware C++ que controle exactamente este circuito."""

    if past_errors:
        errors_ctx = "\n".join(f"- {e[:300]}" for e in past_errors[:3])
        user_message += f"\n\nERRORES PREVIOS A EVITAR:\n{errors_ctx}"

    if compile_error:
        user_message += f"\n\nERROR DEL INTENTO ANTERIOR:\n{compile_error[:500]}\nCorregí el código."

    try:
        response = httpx.post(
            LLM_API,
            headers=get_llm_headers(
                agent_id="hardware-agent",
                agent_name="HardwareAgent"
            ),
            json={
                "model":       LLM_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_message},
                ],
                "temperature": 0.2,
            },
            timeout=180
        )
        response.raise_for_status()
        code = response.json()["choices"][0]["message"]["content"].strip()
        code = _clean_code(code)

        ext      = "ino" if "arduino" in platform or "esp" in platform else "py"
        filename = f"firmware_{device_name.lower().replace(' ', '_')}.{ext}"

        os.makedirs(FIRMWARE_DIR, exist_ok=True)
        path = os.path.join(FIRMWARE_DIR, filename)

        if ext == "ino":
            sketch_dir = os.path.join(FIRMWARE_DIR, filename.replace(".ino", ""))
            os.makedirs(sketch_dir, exist_ok=True)
            path = os.path.join(sketch_dir, filename)

        with open(path, "w", encoding="utf-8") as f:
            f.write(code)

        logger.info(f"[Hardware] Firmware de circuito generado: {filename}")
        return {
            "code":     code,
            "filename": filename,
            "platform": platform,
            "path":     path,
            "dir":      os.path.dirname(path),
        }

    except Exception as e:
        logger.error(f"[Hardware] Error generando firmware de circuito: {e}")
        return {"error": str(e)}
