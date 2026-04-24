# database/design_decisions.py
# Memoria de decisiones de diseño — por qué se eligió cada componente/topología

import os
import sqlite3
import json
from datetime import datetime, timezone
from core.config import SQL_DB_PATH

DB_PATH = SQL_DB_PATH
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


class DesignDecisionsDB:

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS design_decisions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    project     TEXT NOT NULL,
                    component   TEXT,
                    decision    TEXT NOT NULL,
                    reasoning   TEXT NOT NULL,
                    tags        TEXT DEFAULT '[]',
                    created_at  TEXT NOT NULL
                )
            """)
            # Índice para búsqueda por proyecto
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_decisions_project
                ON design_decisions(project)
            """)

    def save(self, project: str, decision: str, reasoning: str,
             component: str = None, tags: list = None) -> int:
        tags = tags or []
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as c:
            cur = c.execute("""
                INSERT INTO design_decisions (project, component, decision, reasoning, tags, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (project, component, decision, reasoning, json.dumps(tags), now))
            return cur.lastrowid

    def get_by_project(self, project: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("""
                SELECT id, project, component, decision, reasoning, tags, created_at
                FROM design_decisions
                WHERE project = ?
                ORDER BY created_at DESC
            """, (project,)).fetchall()
        return [self._row(r) for r in rows]

    def get_all(self, limit: int = 50) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("""
                SELECT id, project, component, decision, reasoning, tags, created_at
                FROM design_decisions
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,)).fetchall()
        return [self._row(r) for r in rows]

    def search(self, query: str, limit: int = 20) -> list[dict]:
        q = f"%{query}%"
        with self._conn() as c:
            rows = c.execute("""
                SELECT id, project, component, decision, reasoning, tags, created_at
                FROM design_decisions
                WHERE decision LIKE ? OR reasoning LIKE ? OR component LIKE ? OR project LIKE ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (q, q, q, q, limit)).fetchall()
        return [self._row(r) for r in rows]

    def delete(self, decision_id: int) -> bool:
        with self._conn() as c:
            c.execute("DELETE FROM design_decisions WHERE id = ?", (decision_id,))
        return True

    def _row(self, r) -> dict:
        return {
            "id":         r[0],
            "project":    r[1],
            "component":  r[2],
            "decision":   r[3],
            "reasoning":  r[4],
            "tags":       json.loads(r[5]) if r[5] else [],
            "created_at": r[6],
        }


# Singleton
_decisions_db: DesignDecisionsDB | None = None

def get_decisions_db() -> DesignDecisionsDB:
    global _decisions_db
    if _decisions_db is None:
        _decisions_db = DesignDecisionsDB()
    return _decisions_db
