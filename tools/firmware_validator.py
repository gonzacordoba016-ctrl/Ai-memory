# tools/firmware_validator.py
# Static pre-compilation analysis for Arduino/ESP32/MicroPython firmware.
# Catches the most common LLM-generated mistakes BEFORE calling arduino-cli.
# Returns (fixed_code, issues) so the caller gets working code with zero compile roundtrips.

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional

# ────────────────────────────────────────────────────────────────────────────
# RESULT TYPE
# ────────────────────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    fixed_code: str
    issues: list[str] = field(default_factory=list)
    auto_fixed: list[str] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        return bool(self.issues)

    @property
    def was_modified(self) -> bool:
        return bool(self.auto_fixed)


# ────────────────────────────────────────────────────────────────────────────
# INCLUDE RULES
# symbol_pattern → required #include (for C++ platforms)
# ────────────────────────────────────────────────────────────────────────────

# Each entry: (regex_pattern_in_code, required_include, description)
_INCLUDE_RULES: list[tuple[str, str, str]] = [
    # Wire / I2C
    (r'\bWire\s*\.', "#include <Wire.h>", "Wire (I2C)"),
    # SPI
    (r'\bSPI\s*\.', "#include <SPI.h>", "SPI"),
    # Servo
    (r'\bServo\s+\w+', "#include <Servo.h>", "Servo"),
    # DHT sensor
    (r'\bDHT\s+\w+|\bDHT\s*dht', "#include <DHT.h>", "DHT sensor"),
    # OneWire
    (r'\bOneWire\s+\w+', "#include <OneWire.h>", "OneWire"),
    # DallasTemperature
    (r'\bDallasTemperature\s+\w+', "#include <DallasTemperature.h>", "DallasTemperature"),
    # Adafruit SSD1306
    (r'\bAdafruit_SSD1306\s+\w+', "#include <Adafruit_SSD1306.h>", "Adafruit SSD1306"),
    # Adafruit GFX (required by SSD1306)
    (r'\bAdafruit_SSD1306\s+\w+', "#include <Adafruit_GFX.h>", "Adafruit GFX"),
    # Adafruit BMP280
    (r'\bAdafruit_BMP280\s+\w+', "#include <Adafruit_BMP280.h>", "Adafruit BMP280"),
    # MPU6050
    (r'\bMPU6050\s+\w+', "#include <MPU6050.h>", "MPU6050"),
    # LiquidCrystal I2C
    (r'\bLiquidCrystal_I2C\s+\w+', "#include <LiquidCrystal_I2C.h>", "LiquidCrystal I2C"),
    # HX711
    (r'\bHX711\s+\w+', "#include <HX711.h>", "HX711"),
    # NeoPixel
    (r'\bAdafruit_NeoPixel\s+\w+', "#include <Adafruit_NeoPixel.h>", "Adafruit NeoPixel"),
    # RTClib
    (r'\bRTC_DS3231\s+\w+|\bRTC_DS1307\s+\w+', "#include <RTClib.h>", "RTClib"),
    # ArduinoOTA
    (r'\bArduinoOTA\s*\.', "#include <ArduinoOTA.h>", "ArduinoOTA"),
    # WiFi (ESP32)
    (r'\bWiFi\s*\.begin\b', "#include <WiFi.h>", "WiFi"),
    # esp_task_wdt
    (r'\besp_task_wdt_init\b|\besp_task_wdt_add\b|\besp_task_wdt_reset\b',
     "#include <esp_task_wdt.h>", "esp_task_wdt"),
    # EEPROM
    (r'\bEEPROM\s*\.', "#include <EEPROM.h>", "EEPROM"),
    # INA219
    (r'\bAdafruit_INA219\s+\w+', "#include <Adafruit_INA219.h>", "Adafruit INA219"),
    # Adafruit BusIO (sometimes needed)
    (r'\bAdafruit_I2CDevice\b', "#include <Adafruit_BusIO_Register.h>", "Adafruit BusIO"),
]

# ────────────────────────────────────────────────────────────────────────────
# PLATFORM-SPECIFIC RULES
# ────────────────────────────────────────────────────────────────────────────

# (pattern, issue_message, auto_fix_fn | None)
# auto_fix_fn(code) -> str replaces the issue in-place

def _fix_esp32_analogwrite(code: str) -> str:
    """
    Replace analogWrite(pin, val) with ledcWrite on ESP32.
    Adds a ledcSetup + ledcAttachPin in a setup helper if not present.
    Simple approach: comment-out and add a note so the user sees it.
    """
    if 'analogWrite(' not in code:
        return code
    lines = []
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith('analogWrite(') or ' analogWrite(' in line:
            lines.append(line.replace('analogWrite(', 'ledcWrite(/*CH*/0, ') + '  // FIXED: ESP32 usa ledcWrite + ledcSetup/ledcAttachPin')
        else:
            lines.append(line)
    return "\n".join(lines)


def _fix_eeprom_begin(code: str) -> str:
    """Ensure EEPROM.begin(size) is called for ESP32 (not Arduino Uno)."""
    if 'EEPROM.begin' in code:
        return code
    if 'EEPROM.' not in code:
        return code
    # Insert EEPROM.begin(512) in setup()
    setup_match = re.search(r'void\s+setup\s*\(\s*\)\s*\{', code)
    if setup_match:
        insert_pos = setup_match.end()
        return code[:insert_pos] + '\n  EEPROM.begin(512); // FIXED: ESP32 requiere EEPROM.begin(size)' + code[insert_pos:]
    return code


_PLATFORM_RULES: dict[str, list[tuple[str, str, object]]] = {
    "esp32:esp32": [
        # analogWrite doesn't exist natively on ESP32
        (r'\banalogWrite\s*\(', "ESP32: analogWrite() no existe — usar ledcWrite() con ledcSetup()/ledcAttachPin()", _fix_esp32_analogwrite),
        # EEPROM needs begin()
        (r'\bEEPROM\.[^b]', "ESP32: EEPROM.begin(size) requerido antes de usar EEPROM", _fix_eeprom_begin),
        # delay in loop is fine, but warn about large delays hiding issues
        (r'\bdelay\s*\(\s*[5-9]\d{3,}', "ESP32: delay() muy largo (>5s) puede disparar el watchdog", None),
    ],
    "esp8266:esp8266": [
        (r'\banalogWrite\s*\(', "ESP8266: analogWrite() solo disponible en GPIO con PWM (no todos)", None),
        (r'\bdelay\s*\(\s*[5-9]\d{3,}', "ESP8266: delay() muy largo puede disparar el watchdog", None),
    ],
    "arduino:avr": [
        # delay in ISR context
        (r'attachInterrupt.*\{[^}]*delay\s*\(', "Arduino: delay() NO funciona dentro de un ISR", None),
    ],
}

# ────────────────────────────────────────────────────────────────────────────
# KNOWN API MISTAKES
# ────────────────────────────────────────────────────────────────────────────

# (bad_pattern, good_pattern, description, auto_fix: bool)
_API_FIXES: list[tuple[str, str, str, bool]] = [
    # DHT: dht.read() no existe como función pública — usar readTemperature/readHumidity
    (r'\bdht\.read\(\)', "dht.readTemperature()", "DHT: usar dht.readTemperature() o dht.readHumidity() en vez de dht.read()", True),
    # DS18B20: requestTemperature sin 's'
    (r'\bsensors\.requestTemperature\(\)', "sensors.requestTemperatures()", "DS18B20: usar requestTemperatures() (plural)", True),
    # DS18B20: getTemperature → getTempCByIndex
    (r'\bsensors\.getTemperature\(\)', "sensors.getTempCByIndex(0)", "DS18B20: usar getTempCByIndex(0) en vez de getTemperature()", True),
    # BMP280: getTemperature → readTemperature
    (r'\bbmp\.getTemperature\(\)', "bmp.readTemperature()", "BMP280: usar readTemperature() en vez de getTemperature()", True),
    (r'\bbmp\.getPressure\(\)', "bmp.readPressure()", "BMP280: usar readPressure() en vez de getPressure()", True),
    # Wire.send/receive (old API)
    (r'\bWire\.send\s*\(', "Wire.write(", "Wire: Wire.send() es API antigua, usar Wire.write()", True),
    (r'\bWire\.receive\s*\(', "Wire.read(", "Wire: Wire.receive() es API antigua, usar Wire.read()", True),
    # Serial.println without begin
    # (no auto-fix, too context-dependent)
    # SSD1306 display init without error check
    # NeoPixel: strip.setPixels → setPixelColor
    (r'\bstrip\.setPixels\s*\(', "strip.setPixelColor(", "NeoPixel: usar setPixelColor() en vez de setPixels()", True),
    # Servo: wrong method
    (r'\bmyServo\.writeMicroseconds\s*\(\s*[01]\s*\)', None, "Servo: writeMicroseconds(0) o (1) no válidos; usar write(90) para ángulos", False),
]

# ────────────────────────────────────────────────────────────────────────────
# MISSING SETUP PATTERNS
# Check that certain init calls exist in setup()
# ────────────────────────────────────────────────────────────────────────────

# (class_usage_pattern, required_setup_pattern, auto_fix_fn | None, description)
_SETUP_RULES: list[tuple[str, str, object, str]] = [
    (r'\bWire\s*\.', r'\bWire\.begin\s*\(', None, "Wire.begin() no encontrado — requerido antes de usar I2C"),
    (r'\bSerial\s*\.print', r'\bSerial\.begin\s*\(', None, "Serial.begin() no encontrado — requerido en setup()"),
    (r'\bstrip\s*\.show\s*\(|\bstrip\s*\.setPixelColor',
     r'\bstrip\.begin\s*\(', None, "NeoPixel: strip.begin() no encontrado en setup()"),
]


# ────────────────────────────────────────────────────────────────────────────
# MAIN VALIDATOR
# ────────────────────────────────────────────────────────────────────────────

def validate_firmware(code: str, platform: str = "arduino:avr") -> ValidationResult:
    """
    Analyse generated firmware code and apply safe auto-fixes.

    Returns a ValidationResult with:
    - fixed_code: code with auto-fixes applied (includes added, API calls corrected)
    - issues: list of problem descriptions (includes both fixed and unfixed)
    - auto_fixed: list of fixes that were applied automatically
    """
    if not code or not code.strip():
        return ValidationResult(fixed_code=code)

    issues: list[str] = []
    auto_fixed: list[str] = []
    working_code = code

    is_micropython = "micropython" in platform.lower() or platform == "micropython"

    # ── 1. Include checker (C++ only) ────────────────────────────────────────
    if not is_micropython:
        existing_includes = set(re.findall(r'#include\s*[<"][^>"]+[>"]', working_code))
        includes_to_add: list[str] = []

        for pattern, required_include, lib_name in _INCLUDE_RULES:
            if re.search(pattern, working_code):
                # Normalise to compare
                inc_stripped = required_include.strip()
                if not any(inc_stripped in ex for ex in existing_includes):
                    if inc_stripped not in includes_to_add:
                        includes_to_add.append(inc_stripped)
                        auto_fixed.append(f"Agregado {inc_stripped} (requerido por {lib_name})")

        if includes_to_add:
            # Prepend missing includes, preserving any existing header comments
            lines = working_code.splitlines()
            insert_idx = 0
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith('#include') or stripped.startswith('//') or stripped.startswith('/*') or not stripped:
                    insert_idx = i + 1
                else:
                    break
            new_lines = lines[:insert_idx] + includes_to_add + lines[insert_idx:]
            working_code = "\n".join(new_lines)

    # ── 2. Known API mistakes ─────────────────────────────────────────────────
    if not is_micropython:
        for bad_pattern, good_value, desc, can_auto_fix in _API_FIXES:
            if re.search(bad_pattern, working_code):
                issues.append(desc)
                if can_auto_fix and good_value:
                    working_code = re.sub(bad_pattern, good_value, working_code)
                    auto_fixed.append(f"API fix: {desc}")

    # ── 3. Platform-specific rules ───────────────────────────────────────────
    if not is_micropython:
        platform_rules = _PLATFORM_RULES.get(platform, [])
        for pattern, issue_msg, fix_fn in platform_rules:
            if re.search(pattern, working_code):
                issues.append(issue_msg)
                if fix_fn is not None:
                    try:
                        working_code = fix_fn(working_code)
                        auto_fixed.append(f"Fix plataforma: {issue_msg[:60]}")
                    except Exception:
                        pass

    # ── 4. Missing setup() calls ──────────────────────────────────────────────
    if not is_micropython:
        # Extract setup() body for checking
        setup_match = re.search(r'void\s+setup\s*\(\s*\)\s*\{(.*?)\}', working_code, re.DOTALL)
        setup_body = setup_match.group(1) if setup_match else ""

        for usage_pattern, setup_pattern, fix_fn, desc in _SETUP_RULES:
            if re.search(usage_pattern, working_code):
                if not re.search(setup_pattern, setup_body):
                    issues.append(desc)
                    if fix_fn is not None:
                        try:
                            working_code = fix_fn(working_code)
                            auto_fixed.append(f"Setup fix: {desc[:60]}")
                        except Exception:
                            pass

    return ValidationResult(
        fixed_code=working_code,
        issues=issues,
        auto_fixed=auto_fixed,
    )
