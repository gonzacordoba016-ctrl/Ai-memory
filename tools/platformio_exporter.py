# tools/platformio_exporter.py
# Genera un proyecto PlatformIO desde firmware guardado en Stratum.
# Produce un ZIP con: platformio.ini, src/main.cpp, README.md

import io
import os
import zipfile
from datetime import datetime

# Mapa fqbn → env de PlatformIO
_FQBN_TO_PIO = {
    "arduino:avr:uno":           ("uno",          "atmelavr",  "arduino"),
    "arduino:avr:mega":          ("megaatmega2560","atmelavr",  "arduino"),
    "arduino:avr:nano":          ("nanoatmega328", "atmelavr",  "arduino"),
    "arduino:avr:leonardo":      ("leonardo",      "atmelavr",  "arduino"),
    "arduino:avr:micro":         ("micro",         "atmelavr",  "arduino"),
    "arduino:megaavr:nona4809":  ("nano_every",    "atmelmegaavr", "arduino"),
    "arduino:samd:arduino_zero_native": ("zero",   "atmelsam",  "arduino"),
    "arduino:samd:mkrwifi1010":  ("mkrwifi1010",   "atmelsam",  "arduino"),
    "arduino:samd:nano_33_iot":  ("nano_33_iot",   "atmelsam",  "arduino"),
    "arduino:sam:arduino_due_x": ("due",           "atmelavr",  "arduino"),
    "esp32:esp32:esp32":         ("esp32dev",      "espressif32","arduino"),
    "esp32:esp32:esp32s3":       ("esp32-s3-devkitc-1", "espressif32", "arduino"),
    "esp32:esp32:esp32s2":       ("esp32-s2-saola-1",   "espressif32", "arduino"),
    "esp32:esp32:esp32c3":       ("esp32-c3-devkitm-1", "espressif32", "arduino"),
    "esp8266:esp8266:nodemcuv2": ("nodemcuv2",    "espressif8266","arduino"),
    "esp8266:esp8266:d1_mini":   ("d1_mini",       "espressif8266","arduino"),
    "rp2040:rp2040:rpipico":     ("pico",          "raspberrypi","arduino"),
    "STMicroelectronics:stm32:GenF4": ("bluepill_f103c8", "ststm32", "arduino"),
}

_DEFAULT_PIO = ("uno", "atmelavr", "arduino")


def _fqbn_to_pio(fqbn: str) -> tuple[str, str, str]:
    """Retorna (board, platform, framework) para PlatformIO dado un fqbn."""
    if not fqbn:
        return _DEFAULT_PIO
    return _FQBN_TO_PIO.get(fqbn, _DEFAULT_PIO)


def _make_platformio_ini(board: str, platform: str, framework: str,
                          device_name: str, monitor_speed: int = 115200) -> str:
    return f"""; PlatformIO Project Configuration
; Generado por Stratum — {datetime.now().strftime('%Y-%m-%d %H:%M')}
; Dispositivo: {device_name}
; https://docs.platformio.org/

[env:{board}]
platform  = {platform}
board     = {board}
framework = {framework}
monitor_speed = {monitor_speed}

; Librerías (agregar si es necesario):
; lib_deps =
;   adafruit/DHT sensor library
;   adafruit/Adafruit Unified Sensor
"""


def _make_readme(device_name: str, task: str, timestamp: str,
                  board: str, fqbn: str) -> str:
    return f"""# {device_name} — Proyecto PlatformIO

Exportado desde **Stratum Hardware Memory Engine**
Fecha: {timestamp}

## Tarea original
{task}

## Cómo abrir
1. Instalar [PlatformIO IDE](https://platformio.org/install/ide?install=vscode) en VS Code
2. Abrir esta carpeta en VS Code
3. PlatformIO detecta `platformio.ini` automáticamente
4. `Ctrl+Shift+P` → **PlatformIO: Upload** para compilar y flashear

## Hardware
- **Dispositivo:** {device_name}
- **Board PlatformIO:** {board}
- **FQBN Arduino CLI:** {fqbn or 'N/A'}

## Archivos
- `platformio.ini` — configuración del proyecto
- `src/main.cpp` — código fuente
"""


def export_platformio_zip(
    device_name: str,
    code: str,
    task: str,
    fqbn: str = "",
    monitor_speed: int = 115200,
) -> bytes:
    """
    Genera un ZIP con estructura de proyecto PlatformIO lista para abrir en VS Code.

    Returns:
        bytes del archivo ZIP
    """
    board, platform, framework = _fqbn_to_pio(fqbn)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    ini_content = _make_platformio_ini(board, platform, framework,
                                        device_name, monitor_speed)
    readme_content = _make_readme(device_name, task, timestamp, board, fqbn)

    # Si el código es .ino (Arduino IDE), adaptarlo a .cpp para PlatformIO
    cpp_code = _ino_to_cpp(code)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("platformio.ini",   ini_content)
        zf.writestr("src/main.cpp",     cpp_code)
        zf.writestr("README.md",        readme_content)
    buf.seek(0)
    return buf.read()


def _ino_to_cpp(code: str) -> str:
    """
    Convierte código Arduino (.ino) a C++ válido para PlatformIO.
    PlatformIO compila .cpp directamente — agrega #include <Arduino.h> si falta.
    """
    if not code:
        return '#include <Arduino.h>\n\nvoid setup() {}\nvoid loop() {}\n'

    lines = code.strip().splitlines()

    has_arduino_h = any("#include <Arduino.h>" in l for l in lines)
    has_setup     = any("void setup" in l for l in lines)
    has_loop      = any("void loop"  in l for l in lines)

    result = []
    if not has_arduino_h:
        result.append("#include <Arduino.h>")
        result.append("")

    result.extend(lines)

    if not has_setup:
        result.extend(["", "void setup() {}", ""])
    if not has_loop:
        result.extend(["", "void loop() {}", ""])

    return "\n".join(result) + "\n"
