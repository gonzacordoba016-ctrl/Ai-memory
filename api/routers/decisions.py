# api/routers/decisions.py
# CRUD de decisiones de diseño — por qué se eligió cada componente o topología

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from database.design_decisions import get_decisions_db

router = APIRouter(prefix="/api/decisions", tags=["decisions"])


class DecisionIn(BaseModel):
    project:   str
    decision:  str
    reasoning: str
    component: Optional[str] = None
    tags:      list[str] = []


@router.get("")
async def list_decisions(
    project: Optional[str] = Query(default=None),
    q:       Optional[str] = Query(default=None),
    limit:   int = Query(default=50),
):
    db = get_decisions_db()
    if q:
        return db.search(q, limit=limit)
    if project:
        return db.get_by_project(project)
    return db.get_all(limit=limit)


@router.post("", status_code=201)
async def save_decision(data: DecisionIn):
    db = get_decisions_db()
    decision_id = db.save(
        project=data.project,
        decision=data.decision,
        reasoning=data.reasoning,
        component=data.component,
        tags=data.tags,
    )
    return {"ok": True, "id": decision_id}


@router.delete("/{decision_id}")
async def delete_decision(decision_id: int):
    get_decisions_db().delete(decision_id)
    return {"ok": True}
