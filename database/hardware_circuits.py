# database/hardware_circuits.py
# Tabla: circuit_context — contexto de circuitos por dispositivo.
# Tabla: circuit_history — snapshots de versiones anteriores.

import sqlite3
import json as _json
import os
from datetime import datetime, timezone
from core.logger import logger
from core.config import SQL_DB_PATH

DB_PATH = SQL_DB_PATH
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


class HardwareCircuitsDB:

    def __init__(self):
        self.db_path = DB_PATH
        self._init_tables()

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def _init_tables(self):
        with self._get_conn() as conn:
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
                    notes        TEXT,
                    version      INTEGER DEFAULT 1,
                    updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, device_name)
                )
            """)
            try:
                conn.execute("ALTER TABLE circuit_context ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'")
                conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_cc_user_device ON circuit_context(user_id, device_name)")
            except Exception:
                pass

            conn.execute("""
                CREATE TABLE IF NOT EXISTS circuit_history (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_name  TEXT NOT NULL,
                    version      INTEGER,
                    snapshot     TEXT,   -- JSON del circuito completo
                    reason       TEXT,
                    timestamp    DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def save_circuit_context(self, device_name: str, context: dict, user_id: str = "default") -> bool:
        """Guarda el contexto completo del circuito para un dispositivo."""
        try:
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
        try:
            ctx = self.get_circuit_context(device_name)
            if not ctx:
                return False
            existing_notes = ctx.get("notes", "")
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
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
        """Formatea el contexto del circuito como string para incluir en el prompt del LLM."""
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

    def count(self) -> int:
        with self._get_conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM circuit_context").fetchone()[0]
