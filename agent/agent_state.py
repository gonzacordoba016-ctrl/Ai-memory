# agent/agent_state.py

from collections import deque

class AgentState:
    def __init__(self):
        self.user_profile = {}
        self.conversation_history: deque = deque(maxlen=20)
        self.context = {}
        self.session_platform: str | None = None
        self.current_firmware_draft: str | None = None

    def add_message(self, role: str, content: str):
        self.conversation_history.append({"role": role, "content": content})

    def get_history(self) -> list:
        return list(self.conversation_history)

    def set_user_fact(self, key, value):
        """
        Guarda datos estructurados del usuario
        ejemplo: name=Gonzalo
        """
        self.user_profile[key] = value

    def get_user_fact(self, key):
        return self.user_profile.get(key)

    def get_all_facts(self):
        return self.user_profile

    def set_platform(self, platform: str):
        self.session_platform = platform

    def get_platform(self) -> str | None:
        return self.session_platform

    def set_firmware_draft(self, code: str):
        self.current_firmware_draft = code

    def get_firmware_draft(self) -> str | None:
        return self.current_firmware_draft