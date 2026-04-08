# api/routers/push.py
# Endpoints para registrar/desregistrar tokens de push notifications.

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from tools.push_notifier import register_token, unregister_token
from core.logger import logger

router = APIRouter(tags=["push"])


class TokenRegister(BaseModel):
    token: str
    platform: Optional[str] = "android"


@router.post("/api/push/register")
async def register_push_token(body: TokenRegister):
    """Registra un token FCM/APNs para recibir push notifications."""
    if not body.token:
        raise HTTPException(400, "Token requerido")
    register_token(body.token, body.platform)
    return {"ok": True}


@router.delete("/api/push/register")
async def unregister_push_token(body: TokenRegister):
    """Elimina un token (logout o desactivar notificaciones)."""
    unregister_token(body.token)
    return {"ok": True}
