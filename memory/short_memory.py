# memory/short_memory.py

from core.config import MAX_SHORT_MEMORY


class ShortMemory:

    def __init__(self):
        self.messages = []

    def add(self, text: str):
        """
        Guarda un mensaje en la memoria corta
        """

        self.messages.append(text)

        if len(self.messages) > MAX_SHORT_MEMORY:
            self.messages.pop(0)

    def get(self):
        """
        Devuelve memoria reciente
        """
        return self.messages

    def clear(self):
        """
        Limpia la memoria corta
        """
        self.messages = []