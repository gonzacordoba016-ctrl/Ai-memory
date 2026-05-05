# database/sql_memory.py

import sqlite3
import threading
import uuid as _uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from database import get_db_path


class SQLMemory:

    def __init__(self, db_path: str = None):
        self.db_path = db_path or get_db_path("memory.db")
        self._facts_seq = 0
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_db()

    # ======================
    # CONEXIÓN
    # ======================

    @contextmanager
    def _get_connection(self):
        with self._lock:
            with self._conn:
                yield self._conn

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

            # Migration: agregar elapsed_ms si no existía
            try:
                conn.execute("ALTER TABLE conversations ADD COLUMN elapsed_ms INTEGER DEFAULT NULL")
            except Exception:
                pass

            conn.execute("CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id)")

            # ── Tabla de sesiones de chat ─────────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id          TEXT PRIMARY KEY,
                    user_id     TEXT NOT NULL DEFAULT 'default',
                    title       TEXT NOT NULL DEFAULT 'Nueva conversación',
                    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_msg_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_user ON chat_sessions(user_id, last_msg_at)")

            # ── Tabla de proyectos activos ────────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id          TEXT PRIMARY KEY,
                    user_id     TEXT NOT NULL DEFAULT 'default',
                    name        TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    mcu         TEXT DEFAULT '',
                    components  TEXT DEFAULT '',
                    active      INTEGER NOT NULL DEFAULT 0,
                    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
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
        self._facts_seq += 1

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
        self._facts_seq += 1

    # ======================
    # CONVERSACIONES
    # ======================

    def store_message(self, role: str, content: str, session_id: str = "default", user_id: str = "default", elapsed_ms: int = None):
        """Guarda un mensaje en el historial de conversaciones."""
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO conversations (user_id, session_id, role, content, elapsed_ms) VALUES (?, ?, ?, ?, ?)",
                (user_id, session_id, role, content, elapsed_ms)
            )
            conn.commit()

    def get_recent_messages(self, limit: int = 10, session_id: str = None, user_id: str = "default") -> list[dict]:
        """Retorna los últimos N mensajes como lista de dicts."""
        with self._get_connection() as conn:
            if session_id:
                rows = conn.execute(
                    "SELECT role, content, timestamp, elapsed_ms FROM conversations "
                    "WHERE user_id = ? AND session_id = ? ORDER BY id DESC LIMIT ?",
                    (user_id, session_id, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT role, content, timestamp, elapsed_ms FROM conversations "
                    "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                    (user_id, limit)
                ).fetchall()
        return [{"role": row[0], "content": row[1], "timestamp": row[2], "elapsed_ms": row[3]} for row in reversed(rows)]

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
    # SESIONES DE CHAT
    # ======================

    def list_sessions(self, user_id: str = "default", limit: int = 50) -> list[dict]:
        """Lista sesiones de chat ordenadas por último mensaje."""
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT s.id, s.title, s.created_at, s.last_msg_at,
                       COUNT(c.id) as msg_count
                FROM chat_sessions s
                LEFT JOIN conversations c ON c.session_id = s.id AND c.user_id = s.user_id
                WHERE s.user_id = ?
                GROUP BY s.id
                ORDER BY s.last_msg_at DESC
                LIMIT ?
            """, (user_id, limit)).fetchall()
        return [{"id": r[0], "title": r[1], "created_at": r[2],
                 "last_msg_at": r[3], "msg_count": r[4]} for r in rows]

    def create_session(self, session_id: str = None, title: str = "Nueva conversación",
                       user_id: str = "default") -> dict:
        """Crea una nueva sesión de chat."""
        sid = session_id or str(_uuid.uuid4())
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO chat_sessions (id, user_id, title) VALUES (?, ?, ?)",
                (sid, user_id, title)
            )
            conn.commit()
        return {"id": sid, "title": title, "user_id": user_id}

    def update_session_title(self, session_id: str, title: str, user_id: str = "default") -> bool:
        """Actualiza el título de una sesión."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE chat_sessions SET title = ? WHERE id = ? AND user_id = ?",
                (title, session_id, user_id)
            )
            conn.commit()
        return True

    def touch_session(self, session_id: str, user_id: str = "default"):
        """Actualiza last_msg_at de la sesión y la crea si no existe."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO chat_sessions (id, user_id, title, last_msg_at)
                VALUES (?, ?, 'Nueva conversación', CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET last_msg_at = CURRENT_TIMESTAMP
            """, (session_id, user_id))
            conn.commit()

    def delete_session(self, session_id: str, user_id: str = "default") -> bool:
        """Elimina una sesión y todos sus mensajes."""
        with self._get_connection() as conn:
            conn.execute(
                "DELETE FROM conversations WHERE session_id = ? AND user_id = ?",
                (session_id, user_id)
            )
            conn.execute(
                "DELETE FROM chat_sessions WHERE id = ? AND user_id = ?",
                (session_id, user_id)
            )
            conn.commit()
        return True

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
    # PROYECTOS ACTIVOS
    # ======================

    def list_projects(self, user_id: str = "default") -> list:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT id, name, description, mcu, components, active, created_at, updated_at "
                "FROM projects WHERE user_id = ? ORDER BY updated_at DESC", (user_id,)
            ).fetchall()
        return [{"id":r[0],"name":r[1],"description":r[2],"mcu":r[3],"components":r[4],"active":bool(r[5]),"created_at":r[6],"updated_at":r[7]} for r in rows]

    def create_project(self, name: str, description: str = "", mcu: str = "", components: str = "", user_id: str = "default") -> dict:
        pid = str(_uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO projects (id, user_id, name, description, mcu, components, active, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)",
                (pid, user_id, name, description, mcu, components, now, now)
            )
            conn.commit()
        return {"id": pid, "name": name, "description": description, "mcu": mcu, "components": components, "active": False}

    def activate_project(self, project_id: str, user_id: str = "default") -> bool:
        with self._get_connection() as conn:
            row = conn.execute("SELECT id FROM projects WHERE id = ? AND user_id = ?", (project_id, user_id)).fetchone()
            if not row:
                return False
            conn.execute("UPDATE projects SET active = 0 WHERE user_id = ?", (user_id,))
            conn.execute("UPDATE projects SET active = 1, updated_at = ? WHERE id = ?",
                         (datetime.now(timezone.utc).isoformat(), project_id))
            conn.commit()
        return True

    def deactivate_projects(self, user_id: str = "default"):
        with self._get_connection() as conn:
            conn.execute("UPDATE projects SET active = 0 WHERE user_id = ?", (user_id,))
            conn.commit()

    def get_active_project(self, user_id: str = "default") -> dict | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id, name, description, mcu, components FROM projects WHERE user_id = ? AND active = 1 LIMIT 1", (user_id,)
            ).fetchone()
        if not row:
            return None
        return {"id": row[0], "name": row[1], "description": row[2], "mcu": row[3], "components": row[4]}

    def update_project(self, project_id: str, data: dict, user_id: str = "default") -> bool:
        fields = {k: v for k, v in data.items() if k in ("name","description","mcu","components")}
        if not fields:
            return True
        sets = ", ".join(f"{k} = ?" for k in fields)
        vals = list(fields.values()) + [datetime.now(timezone.utc).isoformat(), project_id, user_id]
        with self._get_connection() as conn:
            cur = conn.execute(f"UPDATE projects SET {sets}, updated_at = ? WHERE id = ? AND user_id = ?", vals)
            conn.commit()
        return cur.rowcount > 0

    def delete_project(self, project_id: str, user_id: str = "default"):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM projects WHERE id = ? AND user_id = ?", (project_id, user_id))
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