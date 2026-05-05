# database/hardware_firmware.py
# Tabla: firmware_history — historial de programación de dispositivos.

import sqlite3
from core.logger import logger
from database import get_db_path


class HardwareFirmwareDB:

    def __init__(self):
        self.db_path = get_db_path("memory.db")
        self._init_table()

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def _init_table(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS firmware_history (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     TEXT NOT NULL DEFAULT 'default',
                    device_name TEXT NOT NULL,
                    task        TEXT NOT NULL,
                    code        TEXT NOT NULL,
                    filename    TEXT,
                    success     INTEGER DEFAULT 1,
                    serial_out  TEXT,
                    timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP,
                    notes       TEXT
                )
            """)
            try:
                conn.execute("ALTER TABLE firmware_history ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'")
            except Exception:
                pass
            conn.commit()

    def save_firmware(self, device_name: str, task: str, code: str,
                      filename: str = "", success: bool = True,
                      serial_out: str = "", notes: str = "", user_id: str = "default"):
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO firmware_history
                   (user_id, device_name, task, code, filename, success, serial_out, notes)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (user_id, device_name, task, code, filename, int(success), serial_out, notes)
            )
            conn.commit()
        logger.info(f"[HardwareMemory] Firmware guardado: {device_name} — {task[:40]}")

    def get_device_history(self, device_name: str, limit: int = 10) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT task, code, filename, success, serial_out, timestamp, notes
                   FROM firmware_history
                   WHERE device_name = ?
                   ORDER BY id DESC LIMIT ?""",
                (device_name, limit)
            ).fetchall()
        return [
            {
                "task":       r[0],
                "code":       r[1],
                "filename":   r[2],
                "success":    bool(r[3]),
                "serial_out": r[4],
                "timestamp":  r[5],
                "notes":      r[6],
            }
            for r in rows
        ]

    def get_current_firmware(self, device_name: str) -> dict | None:
        with self._get_conn() as conn:
            row = conn.execute(
                """SELECT task, code, filename, timestamp
                   FROM firmware_history
                   WHERE device_name = ? AND success = 1
                   ORDER BY id DESC LIMIT 1""",
                (device_name,)
            ).fetchone()
        if not row:
            return None
        return {"task": row[0], "code": row[1], "filename": row[2], "timestamp": row[3]}

    def get_recent_failures(self, device_name: str, limit: int = 3) -> list[str]:
        """Retorna los errores de compilación más recientes para el dispositivo."""
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT serial_out FROM firmware_history
                   WHERE device_name = ? AND success = 0
                     AND serial_out IS NOT NULL AND serial_out != ''
                   ORDER BY id DESC LIMIT ?""",
                (device_name, limit)
            ).fetchall()
        return [r[0].strip() for r in rows if r[0] and r[0].strip()]

    def get_similar_firmware(self, task: str, limit: int = 3) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT device_name, task, code, timestamp
                   FROM firmware_history
                   WHERE success = 1 AND task LIKE ?
                   ORDER BY id DESC LIMIT ?""",
                (f"%{task[:20]}%", limit)
            ).fetchall()
        return [
            {"device": r[0], "task": r[1], "code": r[2], "timestamp": r[3]}
            for r in rows
        ]

    def count_total(self) -> int:
        with self._get_conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM firmware_history").fetchone()[0]

    def count_success(self) -> int:
        with self._get_conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM firmware_history WHERE success=1").fetchone()[0]
