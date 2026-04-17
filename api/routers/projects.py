# api/routers/projects.py
# Gestión de proyectos activos — contexto global inyectado en cada conversación.

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from database.sql_memory import _default as sql_db
from api.auth import get_current_user

router = APIRouter(prefix="/api/projects", tags=["projects"], dependencies=[Depends(get_current_user)])


@router.get("")
async def list_projects():
    projects = sql_db.list_projects()
    active   = sql_db.get_active_project()
    return {"projects": projects, "active": active}


@router.post("")
async def create_project(body: dict):
    name = (body.get("name") or "").strip()
    if not name:
        return JSONResponse({"error": "name requerido"}, status_code=400)
    p = sql_db.create_project(
        name=name,
        description=body.get("description", ""),
        mcu=body.get("mcu", ""),
        components=body.get("components", ""),
    )
    return p


@router.put("/{project_id}/activate")
@router.post("/{project_id}/activate")
async def activate_project(project_id: str):
    ok = sql_db.activate_project(project_id)
    if not ok:
        return JSONResponse({"error": "proyecto no encontrado"}, status_code=404)
    return {"ok": True, "active_id": project_id}


@router.post("/deactivate")
async def deactivate_projects():
    sql_db.deactivate_projects()
    return {"ok": True}


@router.put("/{project_id}")
async def update_project(project_id: str, body: dict):
    ok = sql_db.update_project(project_id, body)
    if not ok:
        return JSONResponse({"error": "proyecto no encontrado"}, status_code=404)
    return {"ok": True}


@router.delete("/{project_id}")
async def delete_project(project_id: str):
    sql_db.delete_project(project_id)
    return {"ok": True}


@router.get("/active")
async def get_active_project():
    p = sql_db.get_active_project()
    return {"project": p}
