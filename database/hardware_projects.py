# database/hardware_projects.py
# Tabla: project_library — biblioteca de proyectos de firmware.

import sqlite3
import os
from core.logger import logger
from core.config import SQL_DB_PATH

DB_PATH = SQL_DB_PATH
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


class HardwareProjectsDB:

    def __init__(self):
        self.db_path = DB_PATH
        self._init_table()

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def _init_table(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS project_library (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     TEXT NOT NULL DEFAULT 'default',
                    name        TEXT NOT NULL,
                    description TEXT NOT NULL,
                    code        TEXT NOT NULL,
                    platform    TEXT NOT NULL,
                    tags        TEXT,
                    used_count  INTEGER DEFAULT 0,
                    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            try:
                conn.execute("ALTER TABLE project_library ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'")
            except Exception:
                pass
            conn.commit()

    def save_to_library(self, name: str, description: str, code: str,
                        platform: str, tags: list[str] = []) -> int:
        tags_str = ",".join(tags)
        with self._get_conn() as conn:
            existing = conn.execute(
                "SELECT id FROM project_library WHERE name = ?", (name,)
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE project_library
                       SET code=?, description=?, tags=?, updated_at=CURRENT_TIMESTAMP
                       WHERE name=?""",
                    (code, description, tags_str, name)
                )
                project_id = existing[0]
            else:
                cur = conn.execute(
                    """INSERT INTO project_library (name, description, code, platform, tags)
                       VALUES (?,?,?,?,?)""",
                    (name, description, code, platform, tags_str)
                )
                project_id = cur.lastrowid
            conn.commit()
        logger.info(f"[HardwareMemory] Proyecto guardado en biblioteca: {name}")
        return project_id

    def search_library(self, query: str, platform: str = None) -> list[dict]:
        with self._get_conn() as conn:
            if platform:
                rows = conn.execute(
                    """SELECT id, name, description, code, platform, tags, used_count, created_at
                       FROM project_library
                       WHERE platform = ? AND (name LIKE ? OR description LIKE ? OR tags LIKE ?)
                       ORDER BY used_count DESC LIMIT 5""",
                    (platform, f"%{query}%", f"%{query}%", f"%{query}%")
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT id, name, description, code, platform, tags, used_count, created_at
                       FROM project_library
                       WHERE name LIKE ? OR description LIKE ? OR tags LIKE ?
                       ORDER BY used_count DESC LIMIT 5""",
                    (f"%{query}%", f"%{query}%", f"%{query}%")
                ).fetchall()
        return [
            {
                "id": r[0], "name": r[1], "description": r[2],
                "code": r[3], "platform": r[4],
                "tags": r[5].split(",") if r[5] else [],
                "used_count": r[6], "created_at": r[7],
            }
            for r in rows
        ]

    def get_library(self, platform: str = None) -> list[dict]:
        with self._get_conn() as conn:
            if platform:
                rows = conn.execute(
                    """SELECT id, name, description, platform, tags, used_count, created_at
                       FROM project_library WHERE platform = ?
                       ORDER BY used_count DESC""", (platform,)
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT id, name, description, platform, tags, used_count, created_at
                       FROM project_library ORDER BY used_count DESC"""
                ).fetchall()
        return [
            {
                "id": r[0], "name": r[1], "description": r[2],
                "platform": r[3], "tags": r[4].split(",") if r[4] else [],
                "used_count": r[5], "created_at": r[6],
            }
            for r in rows
        ]

    def use_from_library(self, project_id: int) -> dict | None:
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE project_library SET used_count = used_count + 1 WHERE id = ?",
                (project_id,)
            )
            conn.commit()
            row = conn.execute(
                "SELECT name, description, code, platform FROM project_library WHERE id = ?",
                (project_id,)
            ).fetchone()
        if not row:
            return None
        return {"name": row[0], "description": row[1], "code": row[2], "platform": row[3]}

    def delete_from_library(self, project_id: int) -> bool:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM project_library WHERE id = ?", (project_id,))
            conn.commit()
        return True

    def _auto_save_to_library(self, task: str, code: str, device_name: str):
        """Auto-guarda firmware exitoso en la biblioteca de proyectos."""
        try:
            platform = "arduino:avr"
            if "esp32"    in device_name.lower(): platform = "esp32:esp32"
            elif "esp8266" in device_name.lower(): platform = "esp8266:esp8266"
            elif "pico"    in device_name.lower(): platform = "rp2040:rp2040"

            tags = []
            keywords = {
                "led": "led", "blink": "led", "parpadear": "led",
                "temperatura": "sensor", "temperature": "sensor",
                "servo": "servo", "motor": "motor",
                "wifi": "wifi", "bluetooth": "bluetooth",
                "serial": "serial", "sensor": "sensor",
            }
            for kw, tag in keywords.items():
                if kw in task.lower() and tag not in tags:
                    tags.append(tag)

            self.save_to_library(
                name=task[:60], description=task,
                code=code, platform=platform, tags=tags,
            )
        except Exception as e:
            logger.error(f"[HardwareMemory] Error en auto-save library: {e}")

    def count(self) -> int:
        with self._get_conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM project_library").fetchone()[0]
