# api/auth.py
#
# Utilidades JWT para Stratum.
#
# - encode_token / decode_token: operaciones básicas de JWT
# - get_current_user: FastAPI Dependency — retorna user_id del token
#   Si MULTI_USER=false devuelve "default" sin verificar nada.

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from core.config import MULTI_USER, JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_MINUTES
from core.logger import logger

try:
    from jose import jwt, JWTError
    _JOSE_AVAILABLE = True
except ImportError:
    _JOSE_AVAILABLE = False
    logger.warning(
        "[Auth] python-jose no instalado. JWT desactivado — instalar con: "
        "pip install python-jose[cryptography]"
    )

try:
    from passlib.context import CryptContext
    _pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    _PASSLIB_AVAILABLE = True
except ImportError:
    _PASSLIB_AVAILABLE = False
    _pwd_context = None
    logger.warning(
        "[Auth] passlib no instalado. Hashing desactivado — instalar con: "
        "pip install passlib[bcrypt]"
    )

_bearer = HTTPBearer(auto_error=False)

# ── Contraseñas ───────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    if not _PASSLIB_AVAILABLE:
        raise RuntimeError("passlib[bcrypt] no instalado")
    return _pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    if not _PASSLIB_AVAILABLE:
        return plain == hashed  # fallback inseguro para desarrollo
    return _pwd_context.verify(plain, hashed)


# ── Tokens JWT ────────────────────────────────────────────────────────────────

def encode_token(user_id: str, username: str) -> str:
    """Genera un JWT firmado con user_id y username."""
    if not _JOSE_AVAILABLE:
        raise RuntimeError("python-jose[cryptography] no instalado")

    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {
        "sub":      user_id,
        "username": username,
        "exp":      expire,
        "iat":      datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """
    Decodifica y valida un JWT.
    Retorna el payload si es válido, None si expiró o es inválido.
    """
    if not _JOSE_AVAILABLE:
        return None
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None


# ── FastAPI Dependency ────────────────────────────────────────────────────────

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> str:
    """
    FastAPI Dependency que retorna el user_id del token JWT.

    - Si MULTI_USER=false: retorna "default" sin verificar nada.
    - Si MULTI_USER=true:  exige Bearer token válido, retorna user_id del token.
    """
    if not MULTI_USER:
        return "default"

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación requerido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token malformado")

    return user_id
