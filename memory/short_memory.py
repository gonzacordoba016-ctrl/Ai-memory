# memory/short_memory.py

from collections import deque
from core.config import MAX_SHORT_MEMORY


class ShortMemory:

    def __init__(self):
        self.messages: deque[str] = deque(maxlen=MAX_SHORT_MEMORY)

    def add(self, text: str):
        self.messages.append(text)

    def get(self) -> list[str]:
        return list(self.messages)

    def clear(self):
        self.messages.clear()