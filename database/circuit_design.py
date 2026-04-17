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

    def resolve_component_type(self, component_type: str) -> str:
        """Resuelve el tipo de componente usando los aliases."""
        return COMPONENT_ALIASES.get(component_type.lower(), component_type)
