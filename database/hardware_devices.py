# database/hardware_devices.py
# Tabla: hardware_devices — CRUD de dispositivos físicos.

import sqlite3
import os
from core.logger import logger
from core.config import SQL_DB_PATH

DB_PATH = SQL_DB_PATH
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


class HardwareDevicesDB:

    def __init__(self):
        self.db_path = DB_PATH
        self._init_table()

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def _init_table(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hardware_devices (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     TEXT NOT NULL DEFAULT 'default',
                    device_name TEXT NOT NULL,
                    port        TEXT,
                    fqbn        TEXT,
                    platform    TEXT,
                    micropython INTEGER DEFAULT 0,
                    first_seen  DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_seen   DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            for col, definition in [
                ("micropython", "INTEGER DEFAULT 0"),
                ("user_id",     "TEXT NOT NULL DEFAULT 'default'"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE hardware_devices ADD COLUMN {col} {definition}")
                except Exception:
                    pass
            conn.commit()

    def register_device(self, device: dict, user_id: str = "default"):
        micropython = int(bool(device.get("micropython", False)))
        with self._get_conn() as conn:
            existing = conn.execute(
                "SELECT id FROM hardware_devices WHERE device_name = ? AND user_id = ?",
                (device["name"], user_id)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE hardware_devices SET port=?, micropython=?, last_seen=CURRENT_TIMESTAMP "
                    "WHERE device_name=? AND user_id=?",
                    (device.get("port"), micropython, device["name"], user_id)
                )
            else:
                conn.execute(
                    "INSERT INTO hardware_devices (user_id, device_name, port, fqbn, platform, micropython) VALUES (?,?,?,?,?,?)",
                    (user_id, device["name"], device.get("port"), device.get("fqbn"), device.get("platform"), micropython)
                )
            conn.commit()
        logger.info(f"[HardwareMemory] Dispositivo registrado: {device['name']}")

    def get_all_devices(self, user_id: str = "default") -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT device_name, port, fqbn, platform, micropython, first_seen, last_seen "
                "FROM hardware_devices WHERE user_id = ?", (user_id,)
            ).fetchall()
        return [
            {
                "name":        r[0],
                "port":        r[1],
                "fqbn":        r[2],
                "platform":    r[3],
                "micropython": bool(r[4]),
                "first_seen":  r[5],
                "last_seen":   r[6],
            }
            for r in rows
        ]

    def get_device_info(self, device_name: str, user_id: str = "default") -> dict | None:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT device_name, port, fqbn, platform, micropython, first_seen, last_seen "
                "FROM hardware_devices WHERE device_name = ? AND user_id = ?",
                (device_name, user_id)
            ).fetchone()
        if not row:
            return None
        return {
            "name":        row[0],
            "port":        row[1],
            "fqbn":        row[2],
            "platform":    row[3],
            "micropython": bool(row[4]),
            "first_seen":  row[5],
            "last_seen":   row[6],
        }

    def count(self) -> int:
        with self._get_conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM hardware_devices").fetchone()[0]
