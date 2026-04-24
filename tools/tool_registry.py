# tools/tool_registry.py

from tools.web_search import web_search
from tools.file_tools import read_file, write_file, list_files
from tools.code_executor import execute_python
from tools.hardware_detector import detect_device_str
from tools.serial_monitor import read_serial, send_serial
from tools.plugin_loader import plugin_loader
from memory.pdf_memory import ingest_pdf
from datetime import datetime
from core.logger import logger


def get_datetime() -> str:
    """Retorna la fecha y hora actual."""
    return datetime.now().strftime("%A %d de %B de %Y, %H:%M hs")


# ── Herramientas core (siempre disponibles) ───────────────────────────────────

TOOL_FUNCTIONS = {
    "web_search":      web_search,
    "get_datetime":    get_datetime,
    "read_file":       read_file,
    "write_file":      write_file,
    "list_files":      list_files,
    "execute_python":  execute_python,
    "ingest_pdf":      ingest_pdf,
    "detect_hardware": detect_device_str,
    "read_serial":     lambda port, duration=5: read_serial(port, duration=duration),
    "send_serial":     send_serial,
}

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Busca información actualizada en internet. Usá cuando necesites datos recientes, noticias, precios, clima, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "La búsqueda a realizar"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_datetime",
            "description": "Retorna la fecha y hora actual del sistema.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Lee el contenido de un archivo guardado. Los archivos están en la carpeta agent_files/.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Nombre del archivo a leer (ej: notas.txt)"}
                },
                "required": ["filename"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Crea o sobreescribe un archivo con el contenido dado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Nombre del archivo (ej: resumen.txt)"},
                    "content":  {"type": "string", "description": "Contenido a escribir en el archivo"}
                },
                "required": ["filename", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "Lista todos los archivos disponibles en agent_files/.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_python",
            "description": "Ejecuta código Python y retorna el output. Útil para cálculos, transformaciones de datos, generar listas, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Código Python a ejecutar"}
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "detect_hardware",
            "description": "Detecta dispositivos de hardware conectados al PC como Arduino, ESP32, ESP8266, etc.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_serial",
            "description": "Lee el output del monitor serial de un dispositivo conectado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "port":     {"type": "string", "description": "Puerto serial (ej: COM3)"},
                    "duration": {"type": "integer", "description": "Segundos a escuchar (default: 5)"}
                },
                "required": ["port"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_serial",
            "description": "Envía un mensaje al dispositivo via puerto serial.",
            "parameters": {
                "type": "object",
                "properties": {
                    "port":    {"type": "string", "description": "Puerto serial (ej: COM3)"},
                    "message": {"type": "string", "description": "Mensaje a enviar"}
                },
                "required": ["port", "message"]
            }
        }
    },
]

# ── Cargar plugins automáticamente ───────────────────────────────────────────

plugin_loader.load_all()
TOOL_FUNCTIONS.update(plugin_loader.get_functions())
TOOL_DEFINITIONS.extend(plugin_loader.get_definitions())


def execute_tool(name: str, args: dict) -> str:
    """Ejecuta una herramienta por nombre — core o plugin."""
    fn = TOOL_FUNCTIONS.get(name)
    if not fn:
        return f"Herramienta '{name}' no encontrada."
    try:
        return str(fn(**args))
    except Exception as e:
        logger.error(f"[ToolRegistry] Error ejecutando '{name}': {e}")
        return f"Error ejecutando {name}: {e}"