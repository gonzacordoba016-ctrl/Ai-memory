# api/routers/auth.py
#
# Endpoints de autenticación para Stratum.
#
# POST /api/auth/register  — crear usuario
# POST /api/auth/login     — obtener JWT
# GET  /api/auth/me        — info del usuario autenticado
# GET  /api/auth/status    — si multi-user está activo
#
# En modo single-user (MULTI_USER=false) los endpoints de register/login
# siguen funcionando pero el auth no es requerido en el resto de la API.

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.auth import encode_token, hash_password, verify_password, get_current_user
from core.config import MULTI_USER
from core.logger import logger
from database.sql_memory import _default as sql_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Modelos ───────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str = ""


class LoginRequest(BaseModel):
    username: str
    password: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status")
async def auth_status():
    """Retorna si el modo multi-usuario está activo."""
    return {
        "multi_user": MULTI_USER,
        "message": (
            "Autenticación JWT activa" if MULTI_USER
            else "Modo single-user — autenticación desactivada"
        ),
    }


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest):
    """
    Crea un nuevo usuario.
    En modo single-user sigue funcionando pero el token no es requerido en la API.
    """
    # Verificar que no exista ya
    existing = sql_db.get_user_by_username(body.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El usuario '{body.username}' ya existe",
        )

    hashed = hash_password(body.password)
    user   = sql_db.create_user(
        username=body.username,
        password_hash=hashed,
        display_name=body.display_name or body.username,
    )

    logger.info(f"[Auth] Usuario registrado: {body.username} (id={user['user_id']})")
    token = encode_token(user["user_id"], user["username"])

    return {
        "user_id":      user["user_id"],
        "username":     user["username"],
        "display_name": user["display_name"],
        "token":        token,
    }


@router.post("/login")
async def login(body: LoginRequest):
    """Autentica usuario y retorna JWT."""
    user = sql_db.get_user_by_username(body.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
        )

    if not verify_password(body.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
        )

    token = encode_token(user["user_id"], user["username"])
    logger.info(f"[Auth] Login exitoso: {body.username}")

    return {
        "user_id":      user["user_id"],
        "username":     user["username"],
        "display_name": user["display_name"],
        "token":        token,
        "token_type":   "bearer",
    }


@router.get("/me")
async def me(user_id: str = Depends(get_current_user)):
    """Retorna información del usuario autenticado."""
    if user_id == "default":
        return {
            "user_id":      "default",
            "username":     "default",
            "display_name": "Usuario local",
            "multi_user":   False,
        }

    user = sql_db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    return {
        "user_id":      user["user_id"],
        "username":     user["username"],
        "display_name": user["display_name"],
        "multi_user":   True,
    }
