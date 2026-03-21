# database/sql_memory.py

import sqlite3
import os

DB_PATH = os.getenv("MEMORY_DB_PATH", "memory.db")


class SQLMemory:

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    # ======================
    # CONEXIÓN
    # ======================

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    # ======================
    # INICIALIZACIÓN
    # ======================

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS facts (
                    id    INTEGER PRIMARY KEY AUTOINCREMENT,
                    key   TEXT UNIQUE NOT NULL,
                    value TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    role      TEXT NOT NULL,
                    content   TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    # ======================
    # FACTS
    # ======================

    def store_fact(self, key: str, value: str):
        """Guarda o actualiza un hecho clave-valor."""
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO facts (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value)
            )
            conn.commit()

    def get_all_facts(self) -> dict:
        """Retorna todos los hechos como diccionario {clave: valor}."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT key, value FROM facts").fetchall()
        return {row[0]: row[1] for row in rows}

    def delete_fact(self, key: str):
        """Elimina un hecho por su clave."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM facts WHERE key = ?", (key,))
            conn.commit()

    # ======================
    # CONVERSACIONES
    # ======================

    def store_message(self, role: str, content: str):
        """Guarda un mensaje en el historial de conversaciones."""
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO conversations (role, content) VALUES (?, ?)",
                (role, content)
            )
            conn.commit()

    def get_recent_messages(self, limit: int = 10) -> list[dict]:
        """Retorna los últimos N mensajes como lista de dicts."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT role, content FROM conversations "
                "ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
        # Invertir para orden cronológico
        return [{"role": row[0], "content": row[1]} for row in reversed(rows)]

    def clear_conversations(self):
        """Borra todo el historial de conversaciones."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM conversations")
            conn.commit()


# ======================
# FUNCIONES DE COMPATIBILIDAD
# (para módulos que importan funciones sueltas)
# ======================

_default = SQLMemory()

def store_fact(key: str, value: str):
    _default.store_fact(key, value)

def get_all_facts() -> dict:
    return _default.get_all_facts()

def store_message(role: str, content: str):
    _default.store_message(role, content)

def get_recent_messages(limit: int = 10) -> list:
    return _default.get_recent_messages(limit)