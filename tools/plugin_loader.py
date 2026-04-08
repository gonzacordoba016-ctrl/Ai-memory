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
import io
import json
import shutil
import sys
import zipfile
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

            # Leer plugin.json si existe (manifesto opcional)
            manifest = self._read_manifest(path)

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
                "version":     manifest.get("version") or getattr(module, "PLUGIN_VERSION", "1.0"),
                "permissions": manifest.get("permissions", []),
                "manifest":    bool(manifest),
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

    # =========================================================================
    # Manifesto
    # =========================================================================

    def _read_manifest(self, py_path: Path) -> dict:
        """
        Lee el plugin.json junto al .py si existe.
        Retorna dict vacío si no hay manifesto.
        """
        manifest_path = py_path.with_suffix(".json")
        if not manifest_path.exists():
            return {}
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[PluginLoader] Error leyendo {manifest_path.name}: {e}")
            return {}

    # =========================================================================
    # Instalación / desinstalación en caliente
    # =========================================================================

    def install_from_zip(self, zip_bytes: bytes) -> dict:
        """
        Instala un plugin desde un ZIP en memoria.

        Estructura esperada del ZIP:
          plugin.json          ← manifesto obligatorio
          mi_plugin.py         ← código del plugin (debe estar en entry o ser el único .py)
          [otros archivos]     ← recursos opcionales (ignorados)

        Retorna:
          { "status": "ok"|"error", "name": str, "tools": list, "message": str }
        """
        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        except Exception as e:
            return {"status": "error", "message": f"ZIP inválido: {e}"}

        names = zf.namelist()

        # Buscar plugin.json
        json_candidates = [n for n in names if n.endswith("plugin.json") or n == "plugin.json"]
        if not json_candidates:
            return {"status": "error", "message": "ZIP no contiene plugin.json"}

        try:
            manifest = json.loads(zf.read(json_candidates[0]).decode("utf-8"))
        except Exception as e:
            return {"status": "error", "message": f"plugin.json inválido: {e}"}

        # Validar campos mínimos del manifesto
        for field in ("name", "version", "entry"):
            if field not in manifest:
                return {"status": "error", "message": f"plugin.json falta campo '{field}'"}

        plugin_name = manifest["name"]
        entry_file  = manifest["entry"]

        # Buscar el entry .py en el ZIP
        py_candidates = [n for n in names if n.endswith(entry_file)]
        if not py_candidates:
            return {"status": "error", "message": f"Archivo '{entry_file}' no encontrado en el ZIP"}

        # Validar permisos declarados (solo aviso, no bloqueo)
        permissions = manifest.get("permissions", [])
        allowed_permissions = {"serial", "filesystem", "network", "hardware"}
        unknown = set(permissions) - allowed_permissions
        if unknown:
            logger.warning(f"[PluginLoader] Plugin '{plugin_name}' declara permisos desconocidos: {unknown}")

        # Copiar archivos al directorio de plugins
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        dest_py   = PLUGINS_DIR / entry_file
        dest_json = PLUGINS_DIR / (Path(entry_file).stem + ".json")

        dest_py.write_bytes(zf.read(py_candidates[0]))
        dest_json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        logger.info(f"[PluginLoader] Plugin '{plugin_name}' instalado en {dest_py}")

        # Hot reload: desregistrar si ya existía, cargar la nueva versión
        if plugin_name in self._plugins:
            self._unregister(plugin_name)

        success = self._load_plugin(dest_py)
        if not success:
            return {
                "status":  "error",
                "message": f"Archivos copiados pero el plugin '{plugin_name}' no pasó la validación",
            }

        info = self._plugins.get(plugin_name, {})
        return {
            "status":  "ok",
            "name":    plugin_name,
            "tools":   info.get("tools", []),
            "version": info.get("version", ""),
            "message": f"Plugin '{plugin_name}' instalado y cargado exitosamente",
        }

    def uninstall(self, name: str) -> dict:
        """
        Desinstala un plugin por nombre.
        Elimina los archivos .py y .json del directorio de plugins y desregistra las tools.

        Retorna:
          { "status": "ok"|"error", "message": str }
        """
        if name not in self._plugins:
            return {"status": "error", "message": f"Plugin '{name}' no encontrado"}

        info      = self._plugins[name]
        py_path   = PLUGINS_DIR / info["file"]
        json_path = PLUGINS_DIR / (Path(info["file"]).stem + ".json")

        self._unregister(name)

        # Eliminar archivos (sin fallar si no existen)
        for p in (py_path, json_path):
            try:
                if p.exists():
                    p.unlink()
                    logger.info(f"[PluginLoader] Eliminado: {p}")
            except Exception as e:
                logger.warning(f"[PluginLoader] No se pudo eliminar {p}: {e}")

        logger.info(f"[PluginLoader] Plugin '{name}' desinstalado")
        return {"status": "ok", "message": f"Plugin '{name}' desinstalado exitosamente"}

    def _unregister(self, name: str):
        """Elimina del registro en memoria todas las tools de un plugin."""
        if name not in self._plugins:
            return
        tools_to_remove = self._plugins[name].get("tools", [])
        for tool_name in tools_to_remove:
            self._functions.pop(tool_name, None)
            self._definitions = [
                d for d in self._definitions
                if d.get("function", {}).get("name") != tool_name
            ]
        del self._plugins[name]
        logger.info(f"[PluginLoader] Plugin '{name}' desregistrado — tools removidas: {tools_to_remove}")

    def get_plugins_info(self) -> list[dict]:
        """Retorna info de todos los plugins cargados (para la API)."""
        return [
            {
                "name":        name,
                "description": info["description"],
                "file":        info["file"],
                "tools":       info["tools"],
                "version":     info["version"],
                "permissions": info.get("permissions", []),
                "has_manifest": info.get("manifest", False),
            }
            for name, info in self._plugins.items()
        ]


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