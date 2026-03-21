# tools/firmware_flasher.py
#
# Compila y flashea firmware al dispositivo usando arduino-cli.

import subprocess
import os
from core.logger import logger


def compile_firmware(sketch_dir: str, fqbn: str) -> dict:
    """
    Compila un sketch de Arduino.

    Returns:
        {"success": bool, "output": str, "error": str}
    """
    try:
        result = subprocess.run(
            ["arduino-cli", "compile", "--fqbn", fqbn, sketch_dir],
            capture_output=True,
            text=True,
            timeout=120
        )
        success = result.returncode == 0
        output  = result.stdout + result.stderr

        if success:
            logger.info(f"[Hardware] Compilación exitosa: {sketch_dir}")
        else:
            logger.error(f"[Hardware] Error de compilación: {result.stderr}")

        return {
            "success": success,
            "output":  output,
            "error":   result.stderr if not success else "",
        }

    except FileNotFoundError:
        return {
            "success": False,
            "output":  "",
            "error":   "arduino-cli no encontrado. Verificá que esté instalado y en el PATH.",
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "output":  "",
            "error":   "Timeout en compilación. El sketch puede ser demasiado complejo.",
        }
    except Exception as e:
        return {"success": False, "output": "", "error": str(e)}


def flash_firmware(sketch_dir: str, fqbn: str, port: str) -> dict:
    """
    Compila y sube el firmware al dispositivo.

    Returns:
        {"success": bool, "output": str, "error": str}
    """
    try:
        result = subprocess.run(
            [
                "arduino-cli", "compile",
                "--fqbn", fqbn,
                "--upload",
                "--port", port,
                sketch_dir,
            ],
            capture_output=True,
            text=True,
            timeout=180
        )
        success = result.returncode == 0
        output  = result.stdout + result.stderr

        if success:
            logger.info(f"[Hardware] Flash exitoso en {port}")
        else:
            logger.error(f"[Hardware] Error de flash: {result.stderr}")

        return {
            "success": success,
            "output":  output,
            "error":   result.stderr if not success else "",
        }

    except FileNotFoundError:
        return {
            "success": False,
            "output":  "",
            "error":   "arduino-cli no encontrado.",
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "output":  "",
            "error":   "Timeout. Verificá que el dispositivo esté conectado.",
        }
    except Exception as e:
        return {"success": False, "output": "", "error": str(e)}


def install_missing_libraries(error_output: str) -> dict:
    """
    Analiza la salida de error del compilador, detecta librerías faltantes
    e intenta instalarlas automáticamente via arduino-cli.

    Patrones detectados:
      - fatal error: FastLED.h: No such file or directory
      - FastLED.h: No such file or directory
      - #include <FastLED.h>  (en líneas de error de preprocesador)

    Returns:
        {
            "installed": [str],   # Nombres de librerías instaladas exitosamente
            "failed":    [str],   # Librerías que no se pudieron instalar
            "any_installed": bool
        }
    """
    import re

    installed = []
    failed    = []

    # Busca patrones del tipo: 'NombreLib.h: No such file'
    # Cubre tanto 'fatal error:' como líneas de error de gcc/g++
    header_pattern = re.compile(
        r"(?:fatal error|error):\s*([\w./\-]+\.h)\s*:.*?[Nn]o such file",
        re.IGNORECASE
    )

    # Patrón alternativo: líneas de error que mencionan el include directamente
    include_pattern = re.compile(
        r"#include\s*[<\"]([\w./\-]+\.h)[>\"]",
        re.IGNORECASE
    )

    headers_found: set[str] = set()

    for match in header_pattern.findall(error_output):
        headers_found.add(match)

    # Solo busca includes si el error menciona "No such file" (evita falsos positivos)
    if "no such file" in error_output.lower():
        for match in include_pattern.findall(error_output):
            headers_found.add(match)

    if not headers_found:
        logger.info("[Flasher] No se detectaron librerías faltantes en el error.")
        return {"installed": [], "failed": [], "any_installed": False}

    for header in headers_found:
        # Convertir 'FastLED.h' → 'FastLED' para arduino-cli lib install
        lib_name = header.replace(".h", "").replace("/", "_")
        logger.info(f"[Flasher] Intentando instalar librería faltante: {lib_name}")

        try:
            result = subprocess.run(
                ["arduino-cli", "lib", "install", lib_name],
                capture_output=True,
                text=True,
                timeout=120
            )
            if result.returncode == 0:
                logger.info(f"[Flasher] ✓ Librería instalada: {lib_name}")
                installed.append(lib_name)
            else:
                logger.warning(
                    f"[Flasher] No se pudo instalar '{lib_name}': {result.stderr.strip()}"
                )
                failed.append(lib_name)
        except subprocess.TimeoutExpired:
            logger.error(f"[Flasher] Timeout instalando {lib_name}")
            failed.append(lib_name)
        except FileNotFoundError:
            logger.error("[Flasher] arduino-cli no encontrado al intentar instalar librería.")
            failed.append(lib_name)
            break  # Si no hay arduino-cli no tiene sentido seguir iterando

    return {
        "installed":      installed,
        "failed":         failed,
        "any_installed":  len(installed) > 0,
    }


def install_platform(platform: str) -> dict:
    """Instala una plataforma si no está instalada."""
    try:
        result = subprocess.run(
            ["arduino-cli", "core", "install", platform],
            capture_output=True,
            text=True,
            timeout=300
        )
        return {
            "success": result.returncode == 0,
            "output":  result.stdout,
            "error":   result.stderr,
        }
    except Exception as e:
        return {"success": False, "output": "", "error": str(e)}


def list_installed_platforms() -> str:
    """Lista las plataformas instaladas."""
    try:
        result = subprocess.run(
            ["arduino-cli", "core", "list"],
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.stdout or "No hay plataformas instaladas."
    except Exception as e:
        return f"Error: {e}"