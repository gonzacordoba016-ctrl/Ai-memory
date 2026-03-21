# agent/agent_state.py

class AgentState:
    def __init__(self):
        self.user_profile = {}
        self.conversation_history = []
        self.context = {}

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