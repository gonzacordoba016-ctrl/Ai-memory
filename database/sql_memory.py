# database/sql_memory.py

import sqlite3
import os
import uuid as _uuid

from core.config import SQL_DB_PATH

DB_PATH = SQL_DB_PATH



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
            # ── Tabla de usuarios (multi-user) ────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id      TEXT PRIMARY KEY,
                    username     TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    display_name TEXT NOT NULL DEFAULT '',
                    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS facts (
                    id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL DEFAULT 'default',
                    key     TEXT NOT NULL,
                    value   TEXT NOT NULL,
                    UNIQUE(user_id, key)
                )
            """)
            # Migración: agregar user_id a facts si no existía
            try:
                conn.execute("ALTER TABLE facts ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'")
            except Exception:
                pass
            # Migración: asegurar UNIQUE(user_id, key) — DBs viejas tenían UNIQUE(key)
            try:
                conn.execute(
                    "INSERT INTO facts (user_id, key, value) VALUES ('__chk', '__chk', '__chk') "
                    "ON CONFLICT(user_id, key) DO NOTHING"
                )
                conn.execute("DELETE FROM facts WHERE user_id = '__chk'")
            except Exception:
                conn.execute("ALTER TABLE facts RENAME TO facts_old")
                conn.execute("""
                    CREATE TABLE facts (
                        id      INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL DEFAULT 'default',
                        key     TEXT NOT NULL,
                        value   TEXT NOT NULL,
                        UNIQUE(user_id, key)
                    )
                """)
                conn.execute(
                    "INSERT INTO facts (user_id, key, value) "
                    "SELECT COALESCE(user_id, 'default'), key, value FROM facts_old"
                )
                conn.execute("DROP TABLE facts_old")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    TEXT NOT NULL DEFAULT 'default',
                    session_id TEXT NOT NULL DEFAULT 'default',
                    role       TEXT NOT NULL,
                    content    TEXT NOT NULL,
                    timestamp  DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Migraciones de conversations
            for col, definition in [
                ("session_id", "TEXT NOT NULL DEFAULT 'default'"),
                ("user_id",    "TEXT NOT NULL DEFAULT 'default'"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE conversations ADD COLUMN {col} {definition}")
                except Exception:
                    pass

            conn.execute("CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id)")
            conn.commit()

    # ======================
    # FACTS
    # ======================

    def store_fact(self, key: str, value: str, user_id: str = "default"):
        """Guarda o actualiza un hecho clave-valor."""
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO facts (user_id, key, value) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value",
                (user_id, key, value)
            )
            conn.commit()

    def get_all_facts(self, user_id: str = "default") -> dict:
        """Retorna todos los hechos como diccionario {clave: valor}."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT key, value FROM facts WHERE user_id = ?", (user_id,)
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    def delete_fact(self, key: str, user_id: str = "default"):
        """Elimina un hecho por su clave."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM facts WHERE key = ? AND user_id = ?", (key, user_id))
            conn.commit()

    # ======================
    # CONVERSACIONES
    # ======================

    def store_message(self, role: str, content: str, session_id: str = "default", user_id: str = "default"):
        """Guarda un mensaje en el historial de conversaciones."""
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO conversations (user_id, session_id, role, content) VALUES (?, ?, ?, ?)",
                (user_id, session_id, role, content)
            )
            conn.commit()

    def get_recent_messages(self, limit: int = 10, session_id: str = None, user_id: str = "default") -> list[dict]:
        """Retorna los últimos N mensajes como lista de dicts."""
        with self._get_connection() as conn:
            if session_id:
                rows = conn.execute(
                    "SELECT role, content FROM conversations "
                    "WHERE user_id = ? AND session_id = ? ORDER BY id DESC LIMIT ?",
                    (user_id, session_id, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT role, content FROM conversations "
                    "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                    (user_id, limit)
                ).fetchall()
        return [{"role": row[0], "content": row[1]} for row in reversed(rows)]

    def get_conversation_by_session(self, session_id: str, limit: int = 20, user_id: str = "default") -> list[dict]:
        """Retorna el historial de una sesión específica."""
        return self.get_recent_messages(limit=limit, session_id=session_id, user_id=user_id)

    def clear_conversations(self, session_id: str = None, user_id: str = "default"):
        """Borra historial de conversaciones. Si session_id, borra solo esa sesión."""
        with self._get_connection() as conn:
            if session_id:
                conn.execute(
                    "DELETE FROM conversations WHERE user_id = ? AND session_id = ?",
                    (user_id, session_id)
                )
            else:
                conn.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
            conn.commit()

    # ======================
    # USUARIOS
    # ======================

    def create_user(self, username: str, password_hash: str, display_name: str = "") -> dict:
        """Crea un nuevo usuario y retorna su info."""
        user_id = str(_uuid.uuid4())
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO users (user_id, username, password_hash, display_name) VALUES (?,?,?,?)",
                (user_id, username, password_hash, display_name or username)
            )
            conn.commit()
        return {"user_id": user_id, "username": username, "display_name": display_name or username}

    def get_user_by_username(self, username: str) -> dict | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT user_id, username, password_hash, display_name FROM users WHERE username = ?",
                (username,)
            ).fetchone()
        if not row:
            return None
        return {"user_id": row[0], "username": row[1], "password_hash": row[2], "display_name": row[3]}

    def get_user_by_id(self, user_id: str) -> dict | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT user_id, username, display_name FROM users WHERE user_id = ?",
                (user_id,)
            ).fetchone()
        if not row:
            return None
        return {"user_id": row[0], "username": row[1], "display_name": row[2]}


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