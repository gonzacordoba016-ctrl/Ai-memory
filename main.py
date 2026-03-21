# main.py

from dotenv import load_dotenv
load_dotenv()

from core.config import validate_config
try:
    validate_config()
except EnvironmentError as e:
    print(f"\n❌ ERROR DE CONFIGURACIÓN:\n{e}\n")
    exit(1)

import os
import asyncio
from agent.agent_controller import AgentController
from tools.memory_viewer import MemoryViewer
from tools.debug_tools import print_system_info
from memory.pdf_memory import ingest_pdf
from memory.session_summarizer import summarize_session
from core.logger import logger


def print_help():
    print("""
Comandos disponibles:

  /help               mostrar ayuda
  /memory             mostrar datos del usuario
  /history            mostrar conversaciones recientes
  /search <texto>     buscar en memoria vectorial
  /pdf <archivo.pdf>  ingestar un PDF en memoria (debe estar en agent_files/)
  /system             info del sistema
  /exit               guardar sesión y salir
""")


def main():
    print("\n=== AI MEMORY ENGINE ===")
    print("Escribe /help para ver comandos.\n")

    agent  = AgentController()
    viewer = MemoryViewer()

    while True:
        try:
            user_input = input("\nUsuario: ").strip()
        except (KeyboardInterrupt, EOFError):
            user_input = "/exit"

        if not user_input:
            continue

        if user_input == "/exit":
            _exit_gracefully(agent)
            break

        if user_input == "/help":
            print_help()
            continue

        if user_input == "/memory":
            viewer.show_facts()
            continue

        if user_input == "/history":
            viewer.show_recent_conversations()
            continue

        if user_input.startswith("/search "):
            query = user_input[8:].strip()
            if query:
                viewer.search_memories(query)
            else:
                print("Uso: /search <texto>")
            continue

        if user_input.startswith("/pdf "):
            filename = user_input[5:].strip()
            if filename:
                print(f"Procesando '{filename}'...")
                result = ingest_pdf(filename)
                print(result)
            else:
                print("Uso: /pdf <archivo.pdf>")
            continue

        if user_input == "/system":
            print_system_info()
            continue

        try:
            print("\nAgente: ", end="", flush=True)

            def on_token(token: str):
                print(token, end="", flush=True)

            response = asyncio.run(
                agent.process_input(user_input, on_token=on_token)
            )
            print()
        except Exception as e:
            logger.error(f"Error en el agente: {e}")
            print("\nOcurrió un error procesando la solicitud.")


def _exit_gracefully(agent: AgentController):
    history = agent.state.get_history()
    if history:
        print("\nGuardando resumen de la sesión...", end="", flush=True)
        summary = summarize_session(history)
        if summary:
            print(f"\n\nResumen guardado:\n{summary}")
        else:
            print(" (sesión muy corta, no se generó resumen)")

    print("\nConsolidando memoria...", end="", flush=True)
    result = agent.consolidate_on_exit()
    if result.get("consolidated", 0) > 0:
        print(f" {result['consolidated']} episodios consolidados")
    else:
        print(" OK")

    print("\nHasta luego.")


if __name__ == "__main__":
    main()