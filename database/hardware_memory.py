# database/hardware_memory.py
#
# Memoria específica de hardware.
# Guarda firmware, historial, biblioteca de proyectos
# y contexto completo del circuito (componentes, conexiones, notas).

import sqlite3
import json as _json
import os
from datetime import datetime, timezone
from core.logger import logger

from core.config import SQL_DB_PATH

DB_PATH = SQL_DB_PATH



class HardwareMemory:

    def __init__(self):
        self.db_path = DB_PATH
        self._init_db()

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
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
            # Migraciones
            for col, definition in [
                ("micropython", "INTEGER DEFAULT 0"),
                ("user_id",     "TEXT NOT NULL DEFAULT 'default'"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE hardware_devices ADD COLUMN {col} {definition}")
                except Exception:
                    pass

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

            # ── NUEVA TABLA: contexto del circuito ──────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS circuit_context (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id      TEXT NOT NULL DEFAULT 'default',
                    device_name  TEXT NOT NULL,
                    project_name TEXT,
                    description  TEXT,
                    components   TEXT,   -- JSON: [{name, type, pin, notes}]
                    connections  TEXT,   -- JSON: [{from, to, description}]
                    power        TEXT,   -- "5V USB" / "3.3V" / "12V external"
                    notes        TEXT,   -- notas libres del usuario
                    version      INTEGER DEFAULT 1,
                    updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, device_name)
                )
            """)
            try:
                conn.execute("ALTER TABLE circuit_context ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'")
                # Reconstruir el índice UNIQUE si la tabla ya existía sin user_id
                conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_cc_user_device ON circuit_context(user_id, device_name)")
            except Exception:
                pass

            conn.execute("""
                CREATE TABLE IF NOT EXISTS circuit_history (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_name  TEXT NOT NULL,
                    version      INTEGER,
                    snapshot     TEXT,   -- JSON del circuito completo
                    reason       TEXT,   -- por qué cambió
                    timestamp    DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    # ======================
    # DISPOSITIVOS
    # ======================

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
        """
        Retorna los errores de compilación más recientes para el dispositivo.
        Usado por generate_firmware para inyectarlos como contexto al LLM.
        """
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT serial_out FROM firmware_history
                   WHERE device_name = ? AND success = 0
                     AND serial_out IS NOT NULL AND serial_out != ''
                   ORDER BY id DESC LIMIT ?""",
                (device_name, limit)
            ).fetchall()
        return [r[0].strip() for r in rows if r[0] and r[0].strip()]

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
        """Retorna información de un dispositivo registrado por nombre."""
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

    # ======================
    # FIRMWARE
    # ======================

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

        if success and code:
            self._auto_save_to_library(task, code, device_name)

        logger.info(f"[HardwareMemory] Firmware guardado: {device_name} — {task[:40]}")

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

    def get_stats(self) -> dict:
        with self._get_conn() as conn:
            devices  = conn.execute("SELECT COUNT(*) FROM hardware_devices").fetchone()[0]
            total    = conn.execute("SELECT COUNT(*) FROM firmware_history").fetchone()[0]
            success  = conn.execute("SELECT COUNT(*) FROM firmware_history WHERE success=1").fetchone()[0]
            library  = conn.execute("SELECT COUNT(*) FROM project_library").fetchone()[0]
            circuits = conn.execute("SELECT COUNT(*) FROM circuit_context").fetchone()[0]
        return {
            "devices":       devices,
            "total_flashes": total,
            "successful":    success,
            "failed":        total - success,
            "library":       library,
            "circuits":      circuits,
        }

    # ======================
    # CONTEXTO DEL CIRCUITO
    # ======================

    def save_circuit_context(self, device_name: str, context: dict, user_id: str = "default") -> bool:
        """
        Guarda el contexto completo del circuito para un dispositivo.

        context = {
            "project_name": "Estación meteorológica",
            "description":  "Mide temperatura, humedad y presión",
            "components": [
                {"name": "DHT22", "type": "sensor", "pin": "2", "notes": "datos cada 2s"},
                {"name": "LCD 16x2", "type": "display", "pin": "I2C 0x27"},
                {"name": "fotoresistor", "type": "sensor", "pin": "A0"},
            ],
            "connections": [
                {"from": "DHT22 VCC", "to": "5V"},
                {"from": "DHT22 DATA", "to": "Pin 2"},
                {"from": "LCD SDA", "to": "A4"},
            ],
            "power": "5V USB",
            "notes": "El DHT22 da lecturas erróneas con humedad > 80%"
        }
        """
        try:
            # Guardar snapshot en historial antes de actualizar
            existing = self.get_circuit_context(device_name, user_id=user_id)
            if existing:
                version = existing.get("version", 1)
                self._snapshot_circuit(device_name, existing, version)
            else:
                version = 1

            components  = _json.dumps(context.get("components", []),  ensure_ascii=False)
            connections = _json.dumps(context.get("connections", []), ensure_ascii=False)

            with self._get_conn() as conn:
                conn.execute("""
                    INSERT INTO circuit_context
                        (user_id, device_name, project_name, description, components, connections, power, notes, version)
                    VALUES (?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(user_id, device_name) DO UPDATE SET
                        project_name = excluded.project_name,
                        description  = excluded.description,
                        components   = excluded.components,
                        connections  = excluded.connections,
                        power        = excluded.power,
                        notes        = excluded.notes,
                        version      = version + 1,
                        updated_at   = CURRENT_TIMESTAMP
                """, (
                    user_id,
                    device_name,
                    context.get("project_name", ""),
                    context.get("description", ""),
                    components,
                    connections,
                    context.get("power", ""),
                    context.get("notes", ""),
                    version,
                ))
                conn.commit()

            logger.info(f"[HardwareMemory] Circuito guardado: {device_name} — {context.get('project_name','')}")
            return True

        except Exception as e:
            logger.error(f"[HardwareMemory] Error guardando circuito: {e}")
            return False

    def get_circuit_context(self, device_name: str, user_id: str = "default") -> dict | None:
        """Retorna el contexto del circuito de un dispositivo."""
        with self._get_conn() as conn:
            row = conn.execute(
                """SELECT project_name, description, components, connections,
                          power, notes, version, updated_at
                   FROM circuit_context WHERE device_name = ? AND user_id = ?""",
                (device_name, user_id)
            ).fetchone()

        if not row:
            return None

        try:
            components  = _json.loads(row[2]) if row[2] else []
            connections = _json.loads(row[3]) if row[3] else []
        except Exception:
            components  = []
            connections = []

        return {
            "device_name":  device_name,
            "project_name": row[0] or "",
            "description":  row[1] or "",
            "components":   components,
            "connections":  connections,
            "power":        row[4] or "",
            "notes":        row[5] or "",
            "version":      row[6] or 1,
            "updated_at":   row[7] or "",
        }

    def get_all_circuits(self, user_id: str = "default") -> list[dict]:
        """Retorna todos los circuitos registrados (sin código completo)."""
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT device_name, project_name, description, version, updated_at
                   FROM circuit_context WHERE user_id = ? ORDER BY updated_at DESC""",
                (user_id,)
            ).fetchall()
        return [
            {
                "device_name":  r[0],
                "project_name": r[1] or "",
                "description":  r[2] or "",
                "version":      r[3] or 1,
                "updated_at":   r[4] or "",
            }
            for r in rows
        ]

    def get_circuit_history(self, device_name: str) -> list[dict]:
        """Retorna el historial de versiones del circuito."""
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT version, reason, timestamp FROM circuit_history
                   WHERE device_name = ? ORDER BY version DESC LIMIT 10""",
                (device_name,)
            ).fetchall()
        return [
            {"version": r[0], "reason": r[1] or "", "timestamp": r[2]}
            for r in rows
        ]

    def update_circuit_note(self, device_name: str, note: str) -> bool:
        """Agrega una nota al circuito existente."""
        try:
            ctx = self.get_circuit_context(device_name)
            if not ctx:
                return False
            existing_notes = ctx.get("notes", "")
            ts   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
            new_notes = f"{existing_notes}\n[{ts}] {note}".strip()
            with self._get_conn() as conn:
                conn.execute(
                    "UPDATE circuit_context SET notes=?, updated_at=CURRENT_TIMESTAMP WHERE device_name=?",
                    (new_notes, device_name)
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"[HardwareMemory] Error actualizando nota: {e}")
            return False

    def format_circuit_for_prompt(self, device_name: str) -> str:
        """
        Formatea el contexto del circuito como string para incluir en el prompt del LLM.
        Permite que el agente genere firmware más preciso conociendo el circuito.
        """
        ctx = self.get_circuit_context(device_name)
        if not ctx:
            return ""

        lines = [f"Circuito: {ctx['project_name'] or device_name}"]

        if ctx["description"]:
            lines.append(f"Descripción: {ctx['description']}")

        if ctx["power"]:
            lines.append(f"Alimentación: {ctx['power']}")

        if ctx["components"]:
            lines.append("Componentes:")
            for c in ctx["components"]:
                line = f"  - {c.get('name','?')} ({c.get('type','?')})"
                if c.get("pin"):
                    line += f" en pin {c['pin']}"
                if c.get("notes"):
                    line += f" — {c['notes']}"
                lines.append(line)

        if ctx["connections"]:
            lines.append("Conexiones:")
            for conn in ctx["connections"]:
                lines.append(f"  - {conn.get('from','?')} → {conn.get('to','?')}")

        if ctx["notes"]:
            lines.append(f"Notas importantes: {ctx['notes']}")

        return "\n".join(lines)

    def _snapshot_circuit(self, device_name: str, ctx: dict, version: int):
        """Guarda un snapshot del estado anterior del circuito."""
        try:
            with self._get_conn() as conn:
                conn.execute(
                    """INSERT INTO circuit_history (device_name, version, snapshot, reason)
                       VALUES (?,?,?,?)""",
                    (device_name, version, _json.dumps(ctx, ensure_ascii=False), "actualización")
                )
                conn.commit()
        except Exception:
            pass

    # ======================
    # BIBLIOTECA DE PROYECTOS
    # ======================

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
        try:
            platform = "arduino:avr"
            if "esp32"   in device_name.lower(): platform = "esp32:esp32"
            elif "esp8266" in device_name.lower(): platform = "esp8266:esp8266"
            elif "pico"   in device_name.lower(): platform = "rp2040:rp2040"

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


hardware_memory = HardwareMemory()