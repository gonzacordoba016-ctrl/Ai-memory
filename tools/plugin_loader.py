# tools/plugin_loader.py
#
# Sistema de autodiscovery de plugins para Stratum.
# Escanea tools/plugins/ y registra automáticamente cualquier archivo .py
# que cumpla la estructura estándar de plugin.
#
# Para crear un plugin nuevo:
#   1. Crear tools/plugins/mi_plugin.py
#   2. Definir PLUGIN_NAME, PLUGIN_DESCRIPTION y PLUGIN_TOOLS
#   3. Reiniciar Stratum — se registra solo
#
# Estructura mínima de un plugin:
#
#   PLUGIN_NAME = "mi_plugin"
#   PLUGIN_DESCRIPTION = "Qué hace este plugin"
#   PLUGIN_TOOLS = [
#       {
#           "function": mi_funcion,           # callable Python
#           "name":        "nombre_tool",     # nombre que usa el LLM
#           "description": "qué hace",
#           "parameters": {                   # JSON Schema
#               "type": "object",
#               "properties": {
#                   "arg1": {"type": "string", "description": "..."}
#               },
#               "required": ["arg1"]
#           }
#       }
#   ]

import importlib.util
import sys
from pathlib import Path
from core.logger import logger

PLUGINS_DIR = Path(__file__).parent / "plugins"


class PluginLoader:
    """
    Carga y mantiene el registro de plugins.
    Se instancia una vez en tool_registry.py.
    """

    def __init__(self):
        self._plugins:  dict[str, dict]     = {}   # nombre → metadata del plugin
        self._functions: dict[str, callable] = {}   # tool_name → función
        self._definitions: list[dict]        = []   # JSON Schema para el LLM

    # =========================================================================
    # Carga
    # =========================================================================

    def load_all(self) -> int:
        """
        Escanea PLUGINS_DIR y carga todos los plugins válidos.
        Retorna el número de plugins cargados exitosamente.
        """
        if not PLUGINS_DIR.exists():
            PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
            _write_example_plugin()
            logger.info("[PluginLoader] Carpeta plugins/ creada con plugin de ejemplo")
            return 0

        loaded = 0
        for py_file in sorted(PLUGINS_DIR.glob("*.py")):
            if py_file.name.startswith("_"):
                continue   # ignorar __init__.py y archivos privados
            if self._load_plugin(py_file):
                loaded += 1

        if loaded:
            logger.info(
                f"[PluginLoader] {loaded} plugin(s) cargado(s): "
                f"{list(self._plugins.keys())}"
            )
        return loaded

    def _load_plugin(self, path: Path) -> bool:
        """Carga un archivo de plugin y valida su estructura."""
        try:
            spec   = importlib.util.spec_from_file_location(path.stem, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Validar campos obligatorios
            for field in ("PLUGIN_NAME", "PLUGIN_DESCRIPTION", "PLUGIN_TOOLS"):
                if not hasattr(module, field):
                    logger.warning(
                        f"[PluginLoader] {path.name} ignorado — falta '{field}'"
                    )
                    return False

            name  = module.PLUGIN_NAME
            tools = module.PLUGIN_TOOLS

            if not isinstance(tools, list) or not tools:
                logger.warning(f"[PluginLoader] {path.name} — PLUGIN_TOOLS debe ser una lista no vacía")
                return False

            registered_tools = []
            for tool in tools:
                if not self._validate_tool(tool, path.name):
                    continue

                tool_name = tool["name"]

                # Advertir si ya existe (otro plugin registró el mismo nombre)
                if tool_name in self._functions:
                    logger.warning(
                        f"[PluginLoader] Conflicto: '{tool_name}' ya registrado. "
                        f"{path.name} sobreescribe."
                    )

                self._functions[tool_name] = tool["function"]
                self._definitions.append({
                    "type": "function",
                    "function": {
                        "name":        tool_name,
                        "description": tool.get("description", ""),
                        "parameters":  tool.get("parameters", {
                            "type": "object", "properties": {}
                        }),
                    }
                })
                registered_tools.append(tool_name)

            self._plugins[name] = {
                "file":        path.name,
                "description": module.PLUGIN_DESCRIPTION,
                "tools":       registered_tools,
                "version":     getattr(module, "PLUGIN_VERSION", "1.0"),
            }

            logger.info(
                f"[PluginLoader] ✓ Plugin '{name}' cargado — "
                f"tools: {registered_tools}"
            )
            return True

        except Exception as e:
            logger.error(f"[PluginLoader] Error cargando {path.name}: {e}")
            return False

    def _validate_tool(self, tool: dict, filename: str) -> bool:
        """Valida que una tool tenga los campos mínimos."""
        required = ("function", "name", "description")
        for field in required:
            if field not in tool:
                logger.warning(f"[PluginLoader] {filename} — tool sin campo '{field}', ignorada")
                return False
        if not callable(tool["function"]):
            logger.warning(f"[PluginLoader] {filename} — 'function' no es callable")
            return False
        return True

    # =========================================================================
    # API pública
    # =========================================================================

    def get_functions(self) -> dict[str, callable]:
        """Retorna dict {tool_name: callable} de todos los plugins."""
        return dict(self._functions)

    def get_definitions(self) -> list[dict]:
        """Retorna lista de JSON Schema para el LLM."""
        return list(self._definitions)

    def get_plugins_info(self) -> list[dict]:
        """Retorna info de todos los plugins cargados (para la API)."""
        return [
            {
                "name":        name,
                "description": info["description"],
                "file":        info["file"],
                "tools":       info["tools"],
                "version":     info["version"],
            }
            for name, info in self._plugins.items()
        ]

    def execute(self, tool_name: str, args: dict) -> str:
        """Ejecuta una tool de plugin por nombre."""
        fn = self._functions.get(tool_name)
        if not fn:
            return f"Plugin tool '{tool_name}' no encontrada."
        try:
            result = fn(**args)
            return str(result)
        except Exception as e:
            logger.error(f"[PluginLoader] Error ejecutando '{tool_name}': {e}")
            return f"Error ejecutando {tool_name}: {e}"

    def is_plugin_tool(self, tool_name: str) -> bool:
        """Retorna True si el tool_name pertenece a un plugin."""
        return tool_name in self._functions


# ── Plugin de ejemplo ─────────────────────────────────────────────────────────

def _write_example_plugin():
    """Crea un plugin de ejemplo en la carpeta plugins/."""
    example = '''# tools/plugins/example_plugin.py
#
# Plugin de ejemplo para Stratum.
# Copiá este archivo, renombralo y modificalo para crear tu propio plugin.
# Reiniciá Stratum y se registrará automáticamente.

PLUGIN_NAME        = "example"
PLUGIN_DESCRIPTION = "Plugin de ejemplo — muestra la estructura básica"
PLUGIN_VERSION     = "1.0"


def saludo_plugin(nombre: str) -> str:
    """Función de ejemplo que saluda."""
    return f"Hola {nombre} desde el plugin de ejemplo!"


PLUGIN_TOOLS = [
    {
        "function":    saludo_plugin,
        "name":        "saludo_plugin",
        "description": "Saluda a una persona por su nombre (ejemplo de plugin)",
        "parameters": {
            "type": "object",
            "properties": {
                "nombre": {
                    "type":        "string",
                    "description": "Nombre de la persona a saludar"
                }
            },
            "required": ["nombre"]
        }
    }
]
'''
    example_path = PLUGINS_DIR / "example_plugin.py"
    example_path.write_text(example, encoding="utf-8")


# Instancia global — importada por tool_registry.py
plugin_loader = PluginLoader()