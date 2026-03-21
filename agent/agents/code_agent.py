# agent/agents/code_agent.py
#
# Especialista en ejecutar código Python y manejo de archivos.
# Herramientas: execute_python, read_file, write_file, list_files

from agent.agents.base_agent import BaseAgent
from tools.tool_registry import TOOL_DEFINITIONS, execute_tool


_TOOLS = [t for t in TOOL_DEFINITIONS
          if t["function"]["name"] in ("execute_python", "read_file", "write_file", "list_files")]


class CodeAgent(BaseAgent):

    name         = "CodeAgent"
    description  = "Ejecuta código Python, lee y escribe archivos, hace cálculos"
    system_prompt = """Eres un agente especialista en programación y ejecución de código.

Tu función es resolver tareas mediante código Python cuando sea necesario.

Reglas:
- Preferí ejecutar código sobre calcular manualmente
- Guardá resultados importantes en archivos cuando el usuario lo pida
- Explicá brevemente qué hace el código que ejecutás
- Si hay un error en el código, corregilo y volvé a intentar
- Retorná siempre el resultado final de forma clara"""

    def __init__(self, client_fn):
        super().__init__(client_fn, _TOOLS, execute_tool)