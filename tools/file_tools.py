# tools/file_tools.py

import os
from core.logger import logger

# Carpeta base permitida — el agente solo puede leer/escribir acá
FILES_DIR = os.path.abspath("./agent_files")


def _safe_path(filename: str) -> str:
    """Evita path traversal (ej: ../../etc/passwd)."""
    safe = os.path.abspath(os.path.join(FILES_DIR, filename))
    if not safe.startswith(FILES_DIR):
        raise ValueError("Acceso a ruta no permitida.")
    return safe


def read_file(filename: str) -> str:
    """Lee el contenido de un archivo dentro de agent_files/."""
    try:
        os.makedirs(FILES_DIR, exist_ok=True)
        path = _safe_path(filename)
        if not os.path.exists(path):
            return f"El archivo '{filename}' no existe."
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        logger.info(f"Archivo leído: {filename}")
        return content or "(archivo vacío)"
    except Exception as e:
        logger.error(f"Error leyendo archivo: {e}")
        return f"Error al leer '{filename}': {e}"


def write_file(filename: str, content: str) -> str:
    """Escribe o sobreescribe un archivo dentro de agent_files/."""
    try:
        os.makedirs(FILES_DIR, exist_ok=True)
        path = _safe_path(filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Archivo guardado: {filename}")
        return f"Archivo '{filename}' guardado correctamente."
    except Exception as e:
        logger.error(f"Error escribiendo archivo: {e}")
        return f"Error al guardar '{filename}': {e}"


def list_files() -> str:
    """Lista los archivos disponibles en agent_files/."""
    try:
        os.makedirs(FILES_DIR, exist_ok=True)
        files = os.listdir(FILES_DIR)
        if not files:
            return "No hay archivos guardados."
        return "\n".join(f"- {f}" for f in files)
    except Exception as e:
        return f"Error listando archivos: {e}"