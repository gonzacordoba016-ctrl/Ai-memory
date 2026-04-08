# database/intelligence.py
# Gestión de perfiles de IA y fuentes de conocimiento.

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone

from core.logger import logger

DB_PATH = os.getenv("MEMORY_DB_PATH", "./database/memory.db")

DEFAULT_PROFILES = [
    {
        "id": "default-concise",
        "name": "Técnico Conciso",
        "description": "Respuestas cortas y directas. Solo código cuando aplica.",
        "system_prompt": (
            "Eres Stratum, un asistente técnico de hardware especializado en Arduino, "
            "ESP32, Raspberry Pi Pico y microcontroladores.\n"
            "Reglas:\n"
            "- Respondé siempre en el idioma del usuario\n"
            "- Sé extremadamente conciso — una línea de contexto, luego el código o la respuesta directa\n"
            "- No expliques lo obvio ni repitas lo que el usuario ya dijo\n"
            "- Prioriza código funcional sobre explicaciones\n"
            "- Si hay un error, decí qué está mal y cómo arreglarlo, sin rodeos"
        ),
        "is_default": 1,
    },
    {
        "id": "default-mentor",
        "name": "Mentor Arduino",
        "description": "Explica cada decisión, sugiere buenas prácticas, paso a paso.",
        "system_prompt": (
            "Eres Stratum, un mentor técnico especializado en electrónica y programación de microcontroladores.\n"
            "Reglas:\n"
            "- Respondé siempre en el idioma del usuario\n"
            "- Explicá el razonamiento detrás de cada decisión de diseño\n"
            "- Sugiere buenas prácticas y posibles mejoras\n"
            "- Usá analogías cuando ayuden a entender conceptos\n"
            "- Paso a paso cuando la tarea sea compleja\n"
            "- Señalá posibles problemas antes de que ocurran"
        ),
        "is_default": 0,
    },
    {
        "id": "default-debug",
        "name": "Debug Mode",
        "description": "Diagnóstico profundo, hace preguntas, pide logs serial.",
        "system_prompt": (
            "Eres Stratum en modo debug. Tu especialidad es diagnosticar problemas de hardware y firmware.\n"
            "Reglas:\n"
            "- Respondé siempre en el idioma del usuario\n"
            "- Hacé preguntas diagnósticas específicas antes de dar soluciones\n"
            "- Pedí siempre el output serial cuando corresponda\n"
            "- Identificá causas raíz, no solo síntomas\n"
            "- Listá hipótesis en orden de probabilidad\n"
            "- Cuando encontrés el problema, explicá POR QUÉ ocurrió para que no se repita"
        ),
        "is_default": 0,
    },
    {
        "id": "default-production",
        "name": "Producción",
        "description": "Conservador, código probado, sin experimentos.",
        "system_prompt": (
            "Eres Stratum en modo producción. Prioridad: estabilidad y código probado.\n"
            "Reglas:\n"
            "- Respondé siempre en el idioma del usuario\n"
            "- Solo sugerí soluciones bien documentadas y ampliamente probadas\n"
            "- Alertá sobre riesgos antes de proponer cambios\n"
            "- Prioriza backward compatibility\n"
            "- No sugieras bibliotecas experimentales sin advertencia explícita\n"
            "- Incluí siempre manejo de errores en el código generado"
        ),
        "is_default": 0,
    },
]


class IntelligenceDB:

    def __init__(self):
        self._init_tables()
        self._seed_defaults()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(DB_PATH)

    def _init_tables(self):
        try:
            conn = self._conn()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_profiles (
                    id            TEXT PRIMARY KEY,
                    name          TEXT NOT NULL UNIQUE,
                    description   TEXT DEFAULT '',
                    system_prompt TEXT NOT NULL,
                    model_fast    TEXT,
                    model_smart   TEXT,
                    active_sources TEXT DEFAULT '[]',
                    is_default    INTEGER DEFAULT 0,
                    user_id       TEXT DEFAULT 'default',
                    created_at    TEXT,
                    updated_at    TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_sources (
                    id          TEXT PRIMARY KEY,
                    name        TEXT NOT NULL,
                    type        TEXT NOT NULL,
                    content     TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    indexed     INTEGER DEFAULT 0,
                    index_date  TEXT,
                    user_id     TEXT DEFAULT 'default',
                    created_at  TEXT
                )
            """)
            conn.commit()
            conn.close()
            logger.info("[Intelligence] Tablas inicializadas")
        except Exception as e:
            logger.error(f"[Intelligence] Error inicializando tablas: {e}")

    def _seed_defaults(self):
        try:
            conn = self._conn()
            now = datetime.now(timezone.utc).isoformat()
            for p in DEFAULT_PROFILES:
                exists = conn.execute(
                    "SELECT id FROM ai_profiles WHERE id = ?", (p["id"],)
                ).fetchone()
                if not exists:
                    conn.execute(
                        """INSERT INTO ai_profiles
                           (id, name, description, system_prompt, active_sources,
                            is_default, user_id, created_at, updated_at)
                           VALUES (?, ?, ?, ?, '[]', ?, 'default', ?, ?)""",
                        (p["id"], p["name"], p["description"],
                         p["system_prompt"], p["is_default"], now, now)
                    )
            conn.commit()
            conn.close()
            logger.info("[Intelligence] Perfiles por defecto verificados")
        except Exception as e:
            logger.error(f"[Intelligence] Error en seed defaults: {e}")

    # ─── PROFILES ─────────────────────────────────────────────────────────────

    def get_active_profile(self, user_id: str = "default") -> dict | None:
        try:
            conn = self._conn()
            row = conn.execute(
                "SELECT * FROM ai_profiles WHERE is_default = 1 AND user_id = ? LIMIT 1",
                (user_id,)
            ).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT * FROM ai_profiles WHERE user_id = ? LIMIT 1",
                    (user_id,)
                ).fetchone()
            conn.close()
            return self._profile_to_dict(row) if row else None
        except Exception as e:
            logger.error(f"[Intelligence] Error obteniendo perfil activo: {e}")
            return None

    def list_profiles(self, user_id: str = "default") -> list[dict]:
        try:
            conn = self._conn()
            rows = conn.execute(
                "SELECT * FROM ai_profiles WHERE user_id = ? ORDER BY is_default DESC, name ASC",
                (user_id,)
            ).fetchall()
            conn.close()
            return [self._profile_to_dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[Intelligence] Error listando perfiles: {e}")
            return []

    def get_profile(self, profile_id: str) -> dict | None:
        try:
            conn = self._conn()
            row = conn.execute(
                "SELECT * FROM ai_profiles WHERE id = ?", (profile_id,)
            ).fetchone()
            conn.close()
            return self._profile_to_dict(row) if row else None
        except Exception as e:
            logger.error(f"[Intelligence] Error obteniendo perfil {profile_id}: {e}")
            return None

    def create_profile(self, data: dict, user_id: str = "default") -> dict:
        now = datetime.now(timezone.utc).isoformat()
        pid = str(uuid.uuid4())
        conn = self._conn()
        conn.execute(
            """INSERT INTO ai_profiles
               (id, name, description, system_prompt, model_fast, model_smart,
                active_sources, is_default, user_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)""",
            (pid, data["name"], data.get("description", ""), data["system_prompt"],
             data.get("model_fast"), data.get("model_smart"),
             json.dumps(data.get("active_sources", [])), user_id, now, now)
        )
        conn.commit()
        conn.close()
        return self.get_profile(pid)

    def update_profile(self, profile_id: str, data: dict) -> dict | None:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._conn()
        fields, values = [], []
        for key in ("name", "description", "system_prompt", "model_fast", "model_smart"):
            if key in data:
                fields.append(f"{key} = ?")
                values.append(data[key])
        if "active_sources" in data:
            fields.append("active_sources = ?")
            values.append(json.dumps(data["active_sources"]))
        if not fields:
            conn.close()
            return self.get_profile(profile_id)
        fields.append("updated_at = ?")
        values.extend([now, profile_id])
        conn.execute(f"UPDATE ai_profiles SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
        conn.close()
        return self.get_profile(profile_id)

    def activate_profile(self, profile_id: str, user_id: str = "default") -> bool:
        try:
            conn = self._conn()
            conn.execute(
                "UPDATE ai_profiles SET is_default = 0 WHERE user_id = ?", (user_id,)
            )
            conn.execute(
                "UPDATE ai_profiles SET is_default = 1 WHERE id = ?", (profile_id,)
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"[Intelligence] Error activando perfil: {e}")
            return False

    def delete_profile(self, profile_id: str) -> bool:
        try:
            conn = self._conn()
            count = conn.execute("SELECT COUNT(*) FROM ai_profiles").fetchone()[0]
            if count <= 1:
                conn.close()
                return False
            # No borrar perfiles de sistema por defecto
            if profile_id.startswith("default-"):
                conn.close()
                return False
            conn.execute("DELETE FROM ai_profiles WHERE id = ?", (profile_id,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"[Intelligence] Error eliminando perfil: {e}")
            return False

    # ─── SOURCES ──────────────────────────────────────────────────────────────

    def list_sources(self, user_id: str = "default") -> list[dict]:
        try:
            conn = self._conn()
            rows = conn.execute(
                "SELECT * FROM knowledge_sources WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,)
            ).fetchall()
            conn.close()
            return [self._source_to_dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[Intelligence] Error listando fuentes: {e}")
            return []

    def get_source(self, source_id: str) -> dict | None:
        try:
            conn = self._conn()
            row = conn.execute(
                "SELECT * FROM knowledge_sources WHERE id = ?", (source_id,)
            ).fetchone()
            conn.close()
            return self._source_to_dict(row) if row else None
        except Exception as e:
            return None

    def create_source(self, data: dict, user_id: str = "default") -> dict:
        now = datetime.now(timezone.utc).isoformat()
        sid = str(uuid.uuid4())
        conn = self._conn()
        conn.execute(
            """INSERT INTO knowledge_sources
               (id, name, type, content, description, indexed, user_id, created_at)
               VALUES (?, ?, ?, ?, ?, 0, ?, ?)""",
            (sid, data["name"], data["type"],
             data.get("content", ""), data.get("description", ""), user_id, now)
        )
        conn.commit()
        conn.close()
        return self.get_source(sid)

    def mark_indexed(self, source_id: str):
        now = datetime.now(timezone.utc).isoformat()
        conn = self._conn()
        conn.execute(
            "UPDATE knowledge_sources SET indexed = 1, index_date = ? WHERE id = ?",
            (now, source_id)
        )
        conn.commit()
        conn.close()

    def delete_source(self, source_id: str) -> bool:
        try:
            conn = self._conn()
            conn.execute("DELETE FROM knowledge_sources WHERE id = ?", (source_id,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"[Intelligence] Error eliminando fuente: {e}")
            return False

    # ─── HELPERS ──────────────────────────────────────────────────────────────

    def _profile_to_dict(self, row: tuple) -> dict:
        cols = ["id", "name", "description", "system_prompt", "model_fast", "model_smart",
                "active_sources", "is_default", "user_id", "created_at", "updated_at"]
        d = dict(zip(cols, row))
        try:
            d["active_sources"] = json.loads(d.get("active_sources") or "[]")
        except Exception:
            d["active_sources"] = []
        d["is_default"] = bool(d.get("is_default"))
        return d

    def _source_to_dict(self, row: tuple) -> dict:
        cols = ["id", "name", "type", "content", "description",
                "indexed", "index_date", "user_id", "created_at"]
        d = dict(zip(cols, row))
        d["indexed"] = bool(d.get("indexed"))
        return d


intelligence_db = IntelligenceDB()
