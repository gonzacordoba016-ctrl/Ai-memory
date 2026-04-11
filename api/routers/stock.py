# api/routers/stock.py
# CRUD de biblioteca de componentes en stock del ingeniero

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from database.component_stock import get_stock_db

router = APIRouter(prefix="/api/stock", tags=["stock"])


# ── Modelos ──────────────────────────────────────────────────────────────────

class ComponentIn(BaseModel):
    name:         str
    quantity:     int = 0
    category:     Optional[str] = None
    value:        Optional[str] = None
    package:      Optional[str] = None
    supplier:     Optional[str] = None
    supplier_ref: Optional[str] = None
    datasheet:    Optional[str] = None
    notes:        Optional[str] = None
    tags:         list[str] = []

class ComponentUpdate(BaseModel):
    name:         Optional[str] = None
    quantity:     Optional[int] = None
    category:     Optional[str] = None
    value:        Optional[str] = None
    package:      Optional[str] = None
    supplier:     Optional[str] = None
    supplier_ref: Optional[str] = None
    datasheet:    Optional[str] = None
    notes:        Optional[str] = None
    tags:         Optional[list[str]] = None

class QuantityDelta(BaseModel):
    delta: int  # positivo = agregar, negativo = consumir


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("")
async def list_components(
    category:     Optional[str] = Query(default=None),
    in_stock_only: bool = Query(default=False),
    q:            Optional[str] = Query(default=None),
):
    """Lista componentes. Filtra por categoría, stock disponible o búsqueda de texto."""
    db = get_stock_db()
    if q:
        return db.search(q, in_stock_only=in_stock_only)
    return db.get_all(category=category, in_stock_only=in_stock_only)


@router.get("/summary")
async def stock_summary():
    """Resumen del inventario: total, en stock, categorías."""
    return get_stock_db().get_summary()


@router.get("/categories")
async def list_categories():
    """Lista todas las categorías de componentes registradas."""
    return get_stock_db().get_categories()


@router.get("/search")
async def search_components(
    q:            str   = Query(...),
    in_stock_only: bool = Query(default=False),
    limit:        int   = Query(default=50),
):
    """Alias de búsqueda explícito para clientes mobile."""
    return get_stock_db().search(q, in_stock_only=in_stock_only, limit=limit)


@router.post("/{component_id}/adjust")
async def adjust_quantity_qs(component_id: int, delta: int = Query(...)):
    """Ajusta cantidad via query param (conveniente para mobile)."""
    db = get_stock_db()
    if not db.get(component_id):
        raise HTTPException(status_code=404, detail="Componente no encontrado")
    new_qty = db.update_quantity(component_id, delta)
    return {"ok": True, "quantity": new_qty}


@router.post("", status_code=201)
async def add_component(data: ComponentIn):
    """Agrega un nuevo componente al stock."""
    db = get_stock_db()
    component_id = db.add(
        name=data.name,
        quantity=data.quantity,
        category=data.category,
        value=data.value,
        package=data.package,
        supplier=data.supplier,
        supplier_ref=data.supplier_ref,
        datasheet=data.datasheet,
        notes=data.notes,
        tags=data.tags,
    )
    return {"ok": True, "id": component_id}


@router.get("/{component_id}")
async def get_component(component_id: int):
    """Obtiene un componente por ID."""
    c = get_stock_db().get(component_id)
    if not c:
        raise HTTPException(status_code=404, detail="Componente no encontrado")
    return c


@router.put("/{component_id}")
async def update_component(component_id: int, data: ComponentUpdate):
    """Actualiza un componente."""
    db = get_stock_db()
    if not db.get(component_id):
        raise HTTPException(status_code=404, detail="Componente no encontrado")
    db.update(component_id, **data.model_dump(exclude_none=True))
    return {"ok": True}


@router.post("/{component_id}/quantity")
async def adjust_quantity(component_id: int, body: QuantityDelta):
    """Ajusta la cantidad (positivo = agregar, negativo = consumir)."""
    db = get_stock_db()
    if not db.get(component_id):
        raise HTTPException(status_code=404, detail="Componente no encontrado")
    new_qty = db.update_quantity(component_id, body.delta)
    return {"ok": True, "quantity": new_qty}


@router.delete("/{component_id}")
async def delete_component(component_id: int):
    """Elimina un componente del stock."""
    db = get_stock_db()
    if not db.get(component_id):
        raise HTTPException(status_code=404, detail="Componente no encontrado")
    db.delete(component_id)
    return {"ok": True}
