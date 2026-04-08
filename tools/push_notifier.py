# tools/push_notifier.py
# Envío de push notifications via Firebase Cloud Messaging (FCM legacy HTTP API).
# Si FIREBASE_SERVER_KEY no está configurado, las notificaciones push se omiten
# silenciosamente — el resto del sistema sigue funcionando con normalidad.

import os
import sqlite3
from datetime import datetime, timezone

import httpx

from core.logger import logger

FCM_SERVER_KEY = os.getenv("FIREBASE_SERVER_KEY")
FCM_URL        = "https://fcm.googleapis.com/fcm/send"
DB_PATH        = os.getenv("MEMORY_DB_PATH", "./database/memory.db")


# ── Tabla de tokens ───────────────────────────────────────────────────────────

def _init_table():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS push_tokens (
                token      TEXT PRIMARY KEY,
                platform   TEXT DEFAULT 'android',
                user_id    TEXT DEFAULT 'default',
                created_at TEXT
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[Push] Error inicializando tabla: {e}")


_init_table()


def register_token(token: str, platform: str = "android", user_id: str = "default"):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT OR REPLACE INTO push_tokens (token, platform, user_id, created_at) VALUES (?,?,?,?)",
            (token, platform, user_id, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        conn.close()
        logger.info(f"[Push] Token registrado: {token[:16]}... ({platform})")
    except Exception as e:
        logger.error(f"[Push] Error registrando token: {e}")


def unregister_token(token: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM push_tokens WHERE token = ?", (token,))
        conn.commit()
        conn.close()
        logger.info(f"[Push] Token eliminado: {token[:16]}...")
    except Exception as e:
        logger.error(f"[Push] Error eliminando token: {e}")


def get_all_tokens() -> list[str]:
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT token FROM push_tokens").fetchall()
        conn.close()
        return [r[0] for r in rows]
    except Exception as e:
        logger.error(f"[Push] Error obteniendo tokens: {e}")
        return []


# ── Envío FCM ─────────────────────────────────────────────────────────────────

async def send_push_to_all(title: str, body: str, data: dict = None):
    """
    Envía una push notification a todos los dispositivos registrados.
    No hace nada si FIREBASE_SERVER_KEY no está configurado.
    """
    if not FCM_SERVER_KEY:
        return

    tokens = get_all_tokens()
    if not tokens:
        return

    payload = {
        "notification": {"title": title, "body": body},
        "data":         data or {},
        "priority":     "high",
        "registration_ids": tokens,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                FCM_URL,
                json=payload,
                headers={
                    "Authorization": f"key={FCM_SERVER_KEY}",
                    "Content-Type":  "application/json",
                },
            )
            if r.status_code == 200:
                result = r.json()
                logger.info(
                    f"[Push] Enviado a {len(tokens)} device(s) — "
                    f"success: {result.get('success', 0)}, "
                    f"failure: {result.get('failure', 0)}"
                )
            else:
                logger.warning(f"[Push] FCM respondió {r.status_code}")
    except Exception as e:
        logger.error(f"[Push] Error enviando push: {e}")
