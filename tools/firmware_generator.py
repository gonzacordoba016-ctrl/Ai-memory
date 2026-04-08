# tools/firmware_generator.py
#
# Genera código de firmware según la plataforma del dispositivo.
# Usa el LLM para generar código específico y correcto.

import os
import requests
from pathlib import Path
from core.config import LLM_API, LLM_MODEL_SMART as LLM_MODEL, get_llm_headers
from core.logger import logger

FIRMWARE_DIR = os.path.abspath("./agent_files/firmware")

PLATFORM_PROMPTS = {
    "arduino:avr": """Eres un experto en programación de Arduino (C++).
Generá código Arduino válido y completo para el siguiente requerimiento.
Reglas estrictas:
- Solo código C++ válido para Arduino
- Siempre incluí setup() y loop()
- Usá las librerías estándar de Arduino
- Comentá el código brevemente
- No incluyas explicaciones fuera del código
- Devolvé SOLO el código, sin markdown ni backticks""",

    "esp32:esp32": """Eres un experto en programación de ESP32 con Arduino framework.
Generá código C++ válido y completo para ESP32.
Reglas estrictas:
- Código C++ válido para ESP32 con Arduino framework
- Siempre incluí setup() y loop()
- Usá las librerías del ESP32 (WiFi.h, etc.) cuando sea necesario
- Comentá el código brevemente
- No incluyas explicaciones fuera del código
- Devolvé SOLO el código, sin markdown ni backticks""",

    "esp8266:esp8266": """Eres un experto en programación de ESP8266 con Arduino framework.
Generá código C++ válido y completo para ESP8266.
Reglas estrictas:
- Código C++ válido para ESP8266
- Siempre incluí setup() y loop()
- Usá ESP8266WiFi.h para WiFi
- No incluyas explicaciones fuera del código
- Devolvé SOLO el código, sin markdown ni backticks""",

    "micropython": """Eres un experto en MicroPython para microcontroladores.
Generá código MicroPython válido y completo.
Reglas estrictas:
- Solo código MicroPython válido
- Usá las librerías estándar de MicroPython (machine, utime, etc.)
- Comentá el código brevemente
- No incluyas explicaciones fuera del código
- Devolvé SOLO el código, sin markdown ni backticks""",
}

DEFAULT_PROMPT = """Eres un experto en programación de microcontroladores.
Generá código de firmware válido para el siguiente requerimiento.
Devolvé SOLO el código, sin explicaciones ni markdown."""


def generate_firmware(
    description:  str,
    platform:     str,
    device_name:  str       = "",
    past_errors:  list[str] = None,
    compile_error: str      = "",
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

    user_message = f"Dispositivo: {device_name}\nRequerimiento: {description}"

    # Inyectar errores históricos como contexto preventivo
    if past_errors:
        errors_ctx = "\n".join(f"- {e[:300]}" for e in past_errors[:3])
        user_message += f"\n\nERRORES PREVIOS A EVITAR (este device falló antes con):\n{errors_ctx}"

    # Inyectar error del intento actual (reintento)
    if compile_error:
        user_message += f"\n\nERROR DE COMPILACIÓN DEL INTENTO ANTERIOR:\n{compile_error[:500]}\nCorregí el código para resolver este error específico."

    try:
        response = requests.post(
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
            timeout=60
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
) -> dict:
    """
    Genera firmware específico para un circuito dado.
    Reutiliza la lógica de generate_firmware() con un prompt orientado a circuitos.
    """
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
        response = requests.post(
            LLM_API,
            headers=get_llm_headers(
                agent_id="hardware-agent",
                agent_name="HardwareAgent"
            ),
            json={
                "model":       LLM_MODEL,
                "messages": [
                    {"role": "system", "content": CIRCUIT_PROMPT},
                    {"role": "user",   "content": user_message},
                ],
                "temperature": 0.2,
            },
            timeout=60
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
