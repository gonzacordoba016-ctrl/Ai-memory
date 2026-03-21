# tools/plugins/example_plugin.py
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
