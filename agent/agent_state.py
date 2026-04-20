# agent/agent_state.py

class AgentState:
    def __init__(self):
        self.user_profile = {}
        self.conversation_history = []
        self.context = {}
        self.session_platform: str | None = None   # "arduino", "micropython", "esp-idf", etc.
        self.current_firmware_draft: str | None = None  # último firmware generado en sesión

    def add_message(self, role: str, content: str):
        """
        Guarda un mensaje en el historial
        role: 'user' o 'assistant'
        """
        self.conversation_history.append({
            "role": role,
            "content": content
        })

        # limitar historial
        if len(self.conversation_history) > 20:
            self.conversation_history.pop(0)

    def get_history(self):
        return self.conversation_history

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