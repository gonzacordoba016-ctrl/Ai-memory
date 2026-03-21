# tools/memory_viewer.py

from database.sql_memory import SQLMemory
from infrastructure.vector_store import vector_store


class MemoryViewer:

    def __init__(self):

        self.sql_memory = SQLMemory()

    # ======================
    # FACTS
    # ======================

    def show_facts(self):

        print("\n=== USER FACTS ===")

        facts = self.sql_memory.get_all_facts()

        if not facts:
            print("No hay datos del usuario")
            return

        for k, v in facts.items():
            print(f"{k}: {v}")

    # ======================
    # CONVERSATIONS
    # ======================

    def show_recent_conversations(self, limit=10):

        print("\n=== RECENT CONVERSATIONS ===")

        messages = self.sql_memory.get_recent_messages(limit)

        for msg in messages:
            print(f"{msg['role']}: {msg['content']}")

    # ======================
    # VECTOR MEMORIES
    # ======================

    def search_memories(self, query):

        print("\n=== VECTOR MEMORY SEARCH ===")

        results = vector_store.search(query)

        for i, r in enumerate(results, 1):
            print(f"{i}. {r}")