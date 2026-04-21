# database/circuit_design.py

import sqlite3
import json as _json
import os
import pathlib
from typing import Dict, Any, List, Optional
from core.logger import get_logger

logger = get_logger(__name__)
from core.config import SQL_DB_PATH

DB_PATH = SQL_DB_PATH
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


# Librería de componentes — cargada desde data/component_library.json
_lib_data = _json.loads(
    (pathlib.Path(__file__).parent.parent / "data" / "component_library.json").read_text(encoding="utf-8")
)
COMPONENT_LIBRARY: dict = _lib_data["components"]
COMPONENT_ALIASES: dict = _lib_data["aliases"]

class CircuitDesignManager:
    def __init__(self):
        self.db_path = DB_PATH
        self._init_db()
        
    def _get_conn(self):
        return sqlite3.connect(self.db_path)
        
    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS circuit_designs (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     TEXT NOT NULL DEFAULT 'default',
                    name        TEXT NOT NULL,
                    description TEXT,
                    components  TEXT,   -- JSON array
                    nets        TEXT,   -- JSON array
                    metadata    TEXT,   -- JSON object
                    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            try:
                conn.execute("ALTER TABLE circuit_designs ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'")
            except Exception:
                pass

            conn.execute("""
                CREATE TABLE IF NOT EXISTS circuit_versions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    circuit_id  INTEGER,
                    version     INTEGER,
                    snapshot    TEXT,   -- JSON completo del circuito
                    reason      TEXT,
                    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (circuit_id) REFERENCES circuit_designs (id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS circuit_shares (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    token       TEXT UNIQUE NOT NULL,
                    circuit_id  INTEGER NOT NULL,
                    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (circuit_id) REFERENCES circuit_designs (id)
                )
            """)
            conn.commit()
            
    def save_design(self, circuit_data: Dict[str, Any], user_id: str = "default") -> int:
        """Guarda un diseño de circuito y retorna su ID."""
        try:
            name = circuit_data.get("name", "Circuito sin nombre")
            description = circuit_data.get("description", "")
            components = _json.dumps(circuit_data.get("components", []), ensure_ascii=False)
            nets = _json.dumps(circuit_data.get("nets", []), ensure_ascii=False)
            # Mergear metadata extra (source_tool, type, etc.) con power/warnings
            extra_meta = circuit_data.get("metadata", {}) or {}
            metadata = _json.dumps({
                "power":    circuit_data.get("power", extra_meta.get("power", "")),
                "warnings": circuit_data.get("warnings", extra_meta.get("warnings", [])),
                **{k: v for k, v in extra_meta.items() if k not in ("power", "warnings")},
            }, ensure_ascii=False)

            with self._get_conn() as conn:
                cur = conn.execute("""
                    INSERT INTO circuit_designs (user_id, name, description, components, nets, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (user_id, name, description, components, nets, metadata))
                design_id = cur.lastrowid
                conn.commit()
                
            logger.info(f"[CircuitDesign] Diseño guardado: {name} (ID: {design_id})")
            return design_id
            
        except Exception as e:
            logger.error(f"[CircuitDesign] Error guardando diseño: {e}")
            return -1
            
    def get_design(self, design_id: int) -> Optional[Dict[str, Any]]:
        """Obtiene un diseño de circuito por ID."""
        try:
            with self._get_conn() as conn:
                row = conn.execute("""
                    SELECT id, name, description, components, nets, metadata, created_at, updated_at
                    FROM circuit_designs WHERE id = ?
                """, (design_id,)).fetchone()
                
            if not row:
                return None
                
            components = _json.loads(row[3]) if row[3] else []
            nets = _json.loads(row[4]) if row[4] else []
            metadata = _json.loads(row[5]) if row[5] else {}
            
            return {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "components": components,
                "nets": nets,
                "power": metadata.get("power", ""),
                "warnings": metadata.get("warnings", []),
                "positions": metadata.get("positions", {}),
                "created_at": row[6],
                "updated_at": row[7]
            }
            
        except Exception as e:
            logger.error(f"[CircuitDesign] Error obteniendo diseño: {e}")
            return None
            
    def list_designs(self, user_id: str = "default") -> List[Dict[str, Any]]:
        """Lista todos los diseños de circuitos del usuario."""
        try:
            with self._get_conn() as conn:
                rows = conn.execute("""
                    SELECT id, name, description, created_at, updated_at
                    FROM circuit_designs
                    WHERE user_id = ?
                    ORDER BY updated_at DESC
                """, (user_id,)).fetchall()
                
            return [
                {
                    "id": row[0],
                    "name": row[1],
                    "description": row[2],
                    "created_at": row[3],
                    "updated_at": row[4]
                }
                for row in rows
            ]
            
        except Exception as e:
            logger.error(f"[CircuitDesign] Error listando diseños: {e}")
            return []
            
    def save_render_data(self, design_id: int, render_data: Dict[str, Any]) -> bool:
        """Guarda datos de renderizado asociados al diseño."""
        # Esto podría guardarse en una tabla separada si se necesita
        logger.info(f"[CircuitDesign] Datos de render guardados para diseño {design_id}")
        return True
        
    def update_layout(self, design_id: int, positions: dict) -> bool:
        """
        Guarda posiciones personalizadas de componentes en el metadata del diseño.
        positions: { "comp_id": {"x": 100, "y": 200}, ... }
        """
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT metadata FROM circuit_designs WHERE id = ?", (design_id,)
                ).fetchone()
                if not row:
                    return False
                metadata = _json.loads(row[0]) if row[0] else {}
                metadata["positions"] = positions
                conn.execute(
                    "UPDATE circuit_designs SET metadata = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (_json.dumps(metadata, ensure_ascii=False), design_id)
                )
                conn.commit()
            logger.info(f"[CircuitDesign] Layout actualizado para diseño {design_id}")
            return True
        except Exception as e:
            logger.error(f"[CircuitDesign] Error actualizando layout: {e}")
            return False

    # ── Versioning ────────────────────────────────────────────────────────────

    def save_version(self, circuit_id: int, reason: str = "update") -> int:
        """Toma snapshot del circuito actual y lo guarda como nueva versión."""
        try:
            data = self.get_design(circuit_id)
            if not data:
                return -1
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT COALESCE(MAX(version), 0) FROM circuit_versions WHERE circuit_id = ?",
                    (circuit_id,)
                ).fetchone()
                next_ver = (row[0] or 0) + 1
                conn.execute(
                    "INSERT INTO circuit_versions (circuit_id, version, snapshot, reason) VALUES (?, ?, ?, ?)",
                    (circuit_id, next_ver, _json.dumps(data, ensure_ascii=False), reason)
                )
                conn.commit()
            return next_ver
        except Exception as e:
            logger.error(f"[CircuitDesign] Error guardando versión: {e}")
            return -1

    def get_versions(self, circuit_id: int) -> List[Dict]:
        """Lista todas las versiones de un circuito con diff summary."""
        try:
            with self._get_conn() as conn:
                rows = conn.execute(
                    "SELECT version, reason, created_at, snapshot FROM circuit_versions "
                    "WHERE circuit_id = ? ORDER BY version DESC",
                    (circuit_id,)
                ).fetchall()

            result = []
            prev_comps = None
            for row in reversed(rows):
                snap = _json.loads(row[3]) if row[3] else {}
                comps = {c["id"] for c in snap.get("components", [])}
                diff = {}
                if prev_comps is not None:
                    added   = comps - prev_comps
                    removed = prev_comps - comps
                    diff = {"added": list(added), "removed": list(removed)}
                prev_comps = comps
                result.append({
                    "version":    row[0],
                    "reason":     row[1],
                    "created_at": row[2],
                    "components": len(snap.get("components", [])),
                    "nets":       len(snap.get("nets", [])),
                    "diff":       diff,
                })
            result.reverse()
            return result
        except Exception as e:
            logger.error(f"[CircuitDesign] Error listando versiones: {e}")
            return []

    def get_version_snapshot(self, circuit_id: int, version: int) -> Optional[Dict]:
        """Obtiene el snapshot de una versión específica."""
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT snapshot FROM circuit_versions WHERE circuit_id = ? AND version = ?",
                    (circuit_id, version)
                ).fetchone()
            if not row:
                return None
            return _json.loads(row[0])
        except Exception as e:
            logger.error(f"[CircuitDesign] Error obteniendo versión: {e}")
            return None

    def restore_to_version(self, circuit_id: int, version: int) -> bool:
        """Restaura un circuito a una versión anterior, guardando la actual primero."""
        try:
            snap = self.get_version_snapshot(circuit_id, version)
            if not snap:
                return False
            self.save_version(circuit_id, reason=f"auto-save before restore to v{version}")
            components = _json.dumps(snap.get("components", []), ensure_ascii=False)
            nets       = _json.dumps(snap.get("nets", []), ensure_ascii=False)
            metadata   = _json.dumps({
                "power":    snap.get("power", ""),
                "warnings": snap.get("warnings", []),
                "positions": snap.get("positions", {}),
            }, ensure_ascii=False)
            with self._get_conn() as conn:
                conn.execute(
                    "UPDATE circuit_designs SET components=?, nets=?, metadata=?, "
                    "name=?, description=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (components, nets, metadata, snap.get("name", ""), snap.get("description", ""), circuit_id)
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"[CircuitDesign] Error restaurando versión: {e}")
            return False

    # ── Sharing ───────────────────────────────────────────────────────────────

    def create_share(self, circuit_id: int) -> str:
        """Genera un token público para compartir el circuito. Idempotente."""
        import secrets
        try:
            with self._get_conn() as conn:
                existing = conn.execute(
                    "SELECT token FROM circuit_shares WHERE circuit_id = ?", (circuit_id,)
                ).fetchone()
                if existing:
                    return existing[0]
                token = secrets.token_urlsafe(16)
                conn.execute(
                    "INSERT INTO circuit_shares (token, circuit_id) VALUES (?, ?)",
                    (token, circuit_id)
                )
                conn.commit()
            return token
        except Exception as e:
            logger.error(f"[CircuitDesign] Error creando share: {e}")
            return ""

    def get_by_share_token(self, token: str) -> Optional[Dict]:
        """Obtiene el circuito asociado a un token de share."""
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT circuit_id FROM circuit_shares WHERE token = ?", (token,)
                ).fetchone()
            if not row:
                return None
            return self.get_design(row[0])
        except Exception as e:
            logger.error(f"[CircuitDesign] Error obteniendo share: {e}")
            return None

    def revoke_share(self, circuit_id: int) -> bool:
        """Revoca el token de share de un circuito."""
        try:
            with self._get_conn() as conn:
                conn.execute("DELETE FROM circuit_shares WHERE circuit_id = ?", (circuit_id,))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"[CircuitDesign] Error revocando share: {e}")
            return False

    def update_owner(self, design_id: int, user_id: str) -> bool:
        """Asigna user_id al diseño (usado después de parse para multi-usuario)."""
        try:
            with self._get_conn() as conn:
                conn.execute(
                    "UPDATE circuit_designs SET user_id = ? WHERE id = ?",
                    (user_id, design_id)
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"[CircuitDesign] Error actualizando owner: {e}")
            return False

    def update_circuit(self, design_id: int, components: list, nets: list,
                       name: str = None, description: str = None) -> bool:
        """Actualiza componentes/nets de un circuito (editor visual)."""
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT name, description, metadata FROM circuit_designs WHERE id = ?",
                    (design_id,)
                ).fetchone()
                if not row:
                    return False
                metadata = _json.loads(row[2]) if row[2] else {}
                conn.execute(
                    "UPDATE circuit_designs SET components=?, nets=?, name=?, description=?, "
                    "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (
                        _json.dumps(components, ensure_ascii=False),
                        _json.dumps(nets, ensure_ascii=False),
                        name or row[0],
                        description if description is not None else row[1],
                        design_id,
                    )
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"[CircuitDesign] Error actualizando circuito: {e}")
            return False

    def resolve_component_type(self, component_type: str) -> str:
        """Resuelve el tipo de componente usando los aliases."""
        return COMPONENT_ALIASES.get(component_type.lower(), component_type)
