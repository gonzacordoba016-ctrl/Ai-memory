# tools/debug_tools.py

from core.config import (
    EMBEDDING_MODEL,
    VECTOR_COLLECTION,
    VECTOR_DIMENSION,
    SQL_DB_PATH
)

from infrastructure.vector_store import vector_store


def print_system_info():

    print("\n=== SYSTEM INFO ===")

    print("Embedding model:", EMBEDDING_MODEL)
    print("Vector collection:", VECTOR_COLLECTION)
    print("Vector dimension:", VECTOR_DIMENSION)
    print("SQL database:", SQL_DB_PATH)


def test_vector_search(query="hola"):

    print("\n=== VECTOR SEARCH TEST ===")

    results = vector_store.search(query, limit=3)

    if not results:
        print("No se encontraron memorias")

    for i, r in enumerate(results, 1):
        print(f"{i}. {r}")


def print_agent_state(agent):

    print("\n=== AGENT STATE ===")

    print("\nUser facts:")
    for k, v in agent.state.get_all_facts().items():
        print(f"{k}: {v}")

    print("\nConversation history:")
    for msg in agent.state.get_history():
        print(msg["role"], ":", msg["content"])