# database/component_stock.py
# Biblioteca personal de componentes en stock del ingeniero

import sqlite3
import json
from datetime import datetime
from core.config import SQL_DB_PATH

DB_PATH = SQL_DB_PATH


class ComponentStockDB:

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS component_stock (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    name         TEXT NOT NULL,
                    category     TEXT,
                    value        TEXT,
                    package      TEXT,
                    quantity     INTEGER DEFAULT 0,
                    supplier     TEXT,
                    supplier_ref TEXT,
                    datasheet    TEXT,
                    notes        TEXT,
                    tags         TEXT DEFAULT '[]',
                    created_at   TEXT NOT NULL,
                    updated_at   TEXT NOT NULL
                )
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_stock_name
                ON component_stock(name)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_stock_category
                ON component_stock(category)
            """)

    def add(self, name: str, quantity: int = 0, category: str = None,
            value: str = None, package: str = None, supplier: str = None,
            supplier_ref: str = None, datasheet: str = None,
            notes: str = None, tags: list = None) -> int:
        now = datetime.utcnow().isoformat()
        with self._conn() as c:
            cur = c.execute("""
                INSERT INTO component_stock
                (name, category, value, package, quantity, supplier, supplier_ref, datasheet, notes, tags, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (name, category, value, package, quantity, supplier,
                  supplier_ref, datasheet, notes, json.dumps(tags or []), now, now))
            return cur.lastrowid

    def update(self, component_id: int, **kwargs) -> bool:
        allowed = {"name", "category", "value", "package", "quantity",
                   "supplier", "supplier_ref", "datasheet", "notes", "tags"}
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return False
        if "tags" in fields:
            fields["tags"] = json.dumps(fields["tags"])
        fields["updated_at"] = datetime.utcnow().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [component_id]
        with self._conn() as c:
            c.execute(f"UPDATE component_stock SET {set_clause} WHERE id = ?", values)
        return True

    def update_quantity(self, component_id: int, delta: int) -> int:
        with self._conn() as c:
            c.execute("""
                UPDATE component_stock
                SET quantity = MAX(0, quantity + ?), updated_at = ?
                WHERE id = ?
            """, (delta, datetime.utcnow().isoformat(), component_id))
            row = c.execute("SELECT quantity FROM component_stock WHERE id = ?",
                            (component_id,)).fetchone()
        return row[0] if row else 0

    def delete(self, component_id: int) -> bool:
        with self._conn() as c:
            c.execute("DELETE FROM component_stock WHERE id = ?", (component_id,))
        return True

    def get(self, component_id: int) -> dict | None:
        with self._conn() as c:
            row = c.execute("""
                SELECT id, name, category, value, package, quantity, supplier,
                       supplier_ref, datasheet, notes, tags, created_at, updated_at
                FROM component_stock WHERE id = ?
            """, (component_id,)).fetchone()
        return self._row(row) if row else None

    def get_all(self, category: str = None, in_stock_only: bool = False) -> list[dict]:
        query = """
            SELECT id, name, category, value, package, quantity, supplier,
                   supplier_ref, datasheet, notes, tags, created_at, updated_at
            FROM component_stock
        """
        params = []
        conditions = []
        if category:
            conditions.append("category = ?")
            params.append(category)
        if in_stock_only:
            conditions.append("quantity > 0")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY category, name"
        with self._conn() as c:
            rows = c.execute(query, params).fetchall()
        return [self._row(r) for r in rows]

    def search(self, query: str, in_stock_only: bool = False) -> list[dict]:
        q = f"%{query}%"
        stock_filter = "AND quantity > 0" if in_stock_only else ""
        with self._conn() as c:
            rows = c.execute(f"""
                SELECT id, name, category, value, package, quantity, supplier,
                       supplier_ref, datasheet, notes, tags, created_at, updated_at
                FROM component_stock
                WHERE (name LIKE ? OR category LIKE ? OR value LIKE ? OR notes LIKE ?)
                {stock_filter}
                ORDER BY quantity DESC, name
                LIMIT 50
            """, (q, q, q, q)).fetchall()
        return [self._row(r) for r in rows]

    def get_categories(self) -> list[str]:
        with self._conn() as c:
            rows = c.execute("""
                SELECT DISTINCT category FROM component_stock
                WHERE category IS NOT NULL ORDER BY category
            """).fetchall()
        return [r[0] for r in rows]

    def get_summary(self) -> dict:
        with self._conn() as c:
            total = c.execute("SELECT COUNT(*) FROM component_stock").fetchone()[0]
            in_stock = c.execute("SELECT COUNT(*) FROM component_stock WHERE quantity > 0").fetchone()[0]
            cats = c.execute("SELECT COUNT(DISTINCT category) FROM component_stock").fetchone()[0]
        return {"total_components": total, "in_stock": in_stock, "categories": cats}

    def _row(self, r) -> dict:
        return {
            "id":           r[0],
            "name":         r[1],
            "category":     r[2],
            "value":        r[3],
            "package":      r[4],
            "quantity":     r[5],
            "supplier":     r[6],
            "supplier_ref": r[7],
            "datasheet":    r[8],
            "notes":        r[9],
            "tags":         json.loads(r[10]) if r[10] else [],
            "created_at":   r[11],
            "updated_at":   r[12],
        }


# Singleton
_stock_db: ComponentStockDB | None = None

def get_stock_db() -> ComponentStockDB:
    global _stock_db
    if _stock_db is None:
        _stock_db = ComponentStockDB()
    return _stock_db
