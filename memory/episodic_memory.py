# memory/episodic_memory.py

from memory.vector_memory import store_memory
from memory.memory_filter import is_important  # nombre correcto de la función


def store_episode(user_input: str, response: str):
    """Guarda un episodio de conversación si es relevante."""

    if not is_important(user_input):
        return

    episode = (
        f"Evento de conversación:\n"
        f"Usuario: {user_input}\n"
        f"Asistente: {response}"
    )

    store_memory(episode, metadata={"type": "episode"})