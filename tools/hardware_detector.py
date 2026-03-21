# tools/hardware_detector.py

import serial.tools.list_ports
from core.logger import logger

DEVICE_SIGNATURES = {
    # ── Arduino Original ──────────────────────────────────
    (0x2341, 0x0043): {"name": "Arduino Uno R3",      "platform": "arduino:avr",    "fqbn": "arduino:avr:uno"},
    (0x2341, 0x0001): {"name": "Arduino Uno",          "platform": "arduino:avr",    "fqbn": "arduino:avr:uno"},
    (0x2341, 0x0010): {"name": "Arduino Mega 2560",    "platform": "arduino:avr",    "fqbn": "arduino:avr:mega"},
    (0x2341, 0x0036): {"name": "Arduino Leonardo",     "platform": "arduino:avr",    "fqbn": "arduino:avr:leonardo"},
    (0x2341, 0x8036): {"name": "Arduino Leonardo",     "platform": "arduino:avr",    "fqbn": "arduino:avr:leonardo"},
    (0x2341, 0x003D): {"name": "Arduino Due",          "platform": "arduino:sam",    "fqbn": "arduino:sam:arduino_due_x"},
    (0x2341, 0x003E): {"name": "Arduino Due",          "platform": "arduino:sam",    "fqbn": "arduino:sam:arduino_due_x"},
    (0x2341, 0x0042): {"name": "Arduino Mega ADK",     "platform": "arduino:avr",    "fqbn": "arduino:avr:megaADK"},
    (0x2341, 0x0044): {"name": "Arduino Uno Mini",     "platform": "arduino:avr",    "fqbn": "arduino:avr:uno"},
    (0x2341, 0x8037): {"name": "Arduino Micro",        "platform": "arduino:avr",    "fqbn": "arduino:avr:micro"},
    (0x2341, 0x0037): {"name": "Arduino Micro",        "platform": "arduino:avr",    "fqbn": "arduino:avr:micro"},
    (0x2341, 0x804D): {"name": "Arduino Zero",         "platform": "arduino:samd",   "fqbn": "arduino:samd:arduino_zero_native"},
    (0x2341, 0x804E): {"name": "Arduino MKR WiFi 1010","platform": "arduino:samd",   "fqbn": "arduino:samd:mkrwifi1010"},
    (0x2341, 0x8054): {"name": "Arduino Nano 33 IoT",  "platform": "arduino:samd",   "fqbn": "arduino:samd:nano_33_iot"},
    (0x2341, 0x0057): {"name": "Arduino Nano Every",   "platform": "arduino:megaavr","fqbn": "arduino:megaavr:nona4809"},
    (0x2341, 0x0058): {"name": "Arduino Nano Every",   "platform": "arduino:megaavr","fqbn": "arduino:megaavr:nona4809"},

    # ── Arduino Nano clones (CH340) ───────────────────────
    (0x1A86, 0x7523): {"name": "Arduino Nano (CH340)", "platform": "arduino:avr",    "fqbn": "arduino:avr:nano"},

    # ── ESP32 family ──────────────────────────────────────
    (0x10C4, 0xEA60): {"name": "ESP32",                "platform": "esp32:esp32",    "fqbn": "esp32:esp32:esp32"},
    (0x1A86, 0x55D4): {"name": "ESP32-S3",             "platform": "esp32:esp32",    "fqbn": "esp32:esp32:esp32s3"},
    (0x303A, 0x1001): {"name": "ESP32-S2",             "platform": "esp32:esp32",    "fqbn": "esp32:esp32:esp32s2"},
    (0x303A, 0x1002): {"name": "ESP32-C3",             "platform": "esp32:esp32",    "fqbn": "esp32:esp32:esp32c3"},
    (0x303A, 0x0002): {"name": "ESP32-S3 (native USB)","platform": "esp32:esp32",    "fqbn": "esp32:esp32:esp32s3"},
    (0x10C4, 0xEA70): {"name": "ESP32-C3",             "platform": "esp32:esp32",    "fqbn": "esp32:esp32:esp32c3"},

    # ── ESP8266 ───────────────────────────────────────────
    (0x0403, 0x6001): {"name": "ESP8266 (FTDI)",       "platform": "esp8266:esp8266","fqbn": "esp8266:esp8266:generic"},
    (0x0403, 0x6015): {"name": "ESP8266 NodeMCU",      "platform": "esp8266:esp8266","fqbn": "esp8266:esp8266:nodemcuv2"},

    # ── Raspberry Pi Pico / Pico W ────────────────────────
    (0x2E8A, 0x0005): {"name": "Raspberry Pi Pico",    "platform": "rp2040:rp2040",  "fqbn": "rp2040:rp2040:rpipico"},
    (0x2E8A, 0x0003): {"name": "Raspberry Pi Pico W",  "platform": "rp2040:rp2040",  "fqbn": "rp2040:rp2040:rpipicow"},
    (0x2E8A, 0x000A): {"name": "Raspberry Pi Pico 2",  "platform": "rp2040:rp2040",  "fqbn": "rp2040:rp2040:rpipico2"},

    # ── STM32 ─────────────────────────────────────────────
    (0x0483, 0x5740): {"name": "STM32 (Virtual COM)",  "platform": "STMicroelectronics:stm32", "fqbn": "STMicroelectronics:stm32:GenF4"},
    (0x0483, 0xDF11): {"name": "STM32 (DFU mode)",     "platform": "STMicroelectronics:stm32", "fqbn": "STMicroelectronics:stm32:GenF4"},

    # ── Seeed XIAO ────────────────────────────────────────
    (0x2886, 0x002F): {"name": "Seeed XIAO SAMD21",    "platform": "Seeeduino:samd",  "fqbn": "Seeeduino:samd:seeed_XIAO_m0"},
    (0x2886, 0x0045): {"name": "Seeed XIAO RP2040",    "platform": "rp2040:rp2040",   "fqbn": "rp2040:rp2040:seeed_xiao_rp2040"},
    (0x2886, 0x0044): {"name": "Seeed XIAO ESP32C3",   "platform": "esp32:esp32",     "fqbn": "esp32:esp32:XIAO_ESP32C3"},
    (0x2886, 0x0056): {"name": "Seeed XIAO ESP32S3",   "platform": "esp32:esp32",     "fqbn": "esp32:esp32:XIAO_ESP32S3"},

    # ── Teensy ────────────────────────────────────────────
    (0x16C0, 0x0483): {"name": "Teensy (Serial)",      "platform": "teensy:avr",      "fqbn": "teensy:avr:teensy41"},
    (0x16C0, 0x0486): {"name": "Teensy (HalfKay)",     "platform": "teensy:avr",      "fqbn": "teensy:avr:teensy41"},

    # ── Adafruit ──────────────────────────────────────────
    (0x239A, 0x0001): {"name": "Adafruit Feather M0",  "platform": "adafruit:samd",   "fqbn": "adafruit:samd:adafruit_feather_m0"},
    (0x239A, 0x800B): {"name": "Adafruit Feather M4",  "platform": "adafruit:samd",   "fqbn": "adafruit:samd:adafruit_feather_m4"},
    (0x239A, 0x80CB): {"name": "Adafruit QT Py RP2040","platform": "rp2040:rp2040",   "fqbn": "rp2040:rp2040:adafruit_qtpy_rp2040"},
}

# Plataformas requeridas por dispositivo
PLATFORM_INSTALL_CMDS = {
    "arduino:avr":                  "arduino-cli core install arduino:avr",
    "arduino:sam":                  "arduino-cli core install arduino:sam",
    "arduino:samd":                 "arduino-cli core install arduino:samd",
    "arduino:megaavr":              "arduino-cli core install arduino:megaavr",
    "esp32:esp32":                  "arduino-cli core install esp32:esp32 --additional-urls https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json",
    "esp8266:esp8266":              "arduino-cli core install esp8266:esp8266 --additional-urls https://arduino.esp8266.com/stable/package_esp8266com_index.json",
    "rp2040:rp2040":                "arduino-cli core install rp2040:rp2040 --additional-urls https://github.com/earlephilhower/arduino-pico/releases/download/global/package_rp2040_index.json",
    "STMicroelectronics:stm32":     "arduino-cli core install STMicroelectronics:stm32 --additional-urls https://raw.githubusercontent.com/stm32duino/BoardManagerFiles/main/package_stmicroelectronics_index.json",
    "Seeeduino:samd":               "arduino-cli core install Seeeduino:samd --additional-urls https://files.seeedstudio.com/arduino/package_seeeduino_boards_index.json",
}


def detect_devices() -> list[dict]:
    devices = []
    ports   = serial.tools.list_ports.comports()

    for port in ports:
        vid = port.vid
        pid = port.pid

        if vid and pid:
            key  = (vid, pid)
            info = DEVICE_SIGNATURES.get(key)

            if info:
                device = {
                    "port":         port.device,
                    "name":         info["name"],
                    "platform":     info["platform"],
                    "fqbn":         info["fqbn"],
                    "vid":          hex(vid),
                    "pid":          hex(pid),
                    "description":  port.description,
                    "install_cmd":  PLATFORM_INSTALL_CMDS.get(info["platform"], ""),
                }
            else:
                device = {
                    "port":         port.device,
                    "name":         f"Desconocido ({hex(vid)}:{hex(pid)})",
                    "platform":     None,
                    "fqbn":         None,
                    "vid":          hex(vid),
                    "pid":          hex(pid),
                    "description":  port.description,
                    "install_cmd":  "",
                }
            devices.append(device)
            logger.info(f"[Hardware] Detectado: {device['name']} en {port.device}")

    if not devices:
        logger.info("[Hardware] No se detectaron dispositivos")

    return devices


def detect_device_str() -> str:
    devices = detect_devices()
    if not devices:
        return "No se detectaron dispositivos. Verificá que el cable USB esté conectado."
    lines = []
    for d in devices:
        lines.append(
            f"- {d['name']} en {d['port']}"
            + (f" (plataforma: {d['platform']})" if d['platform'] else " (desconocido)")
        )
    return "Dispositivos detectados:\n" + "\n".join(lines)


def get_supported_platforms() -> list[str]:
    """Lista todas las plataformas soportadas."""
    return list(set(v["platform"] for v in DEVICE_SIGNATURES.values() if v.get("platform")))