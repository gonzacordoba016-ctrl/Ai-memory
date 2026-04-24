# agent/session_continuity.py
# Generates a context card for new sessions by looking at recent past work.
# The card is sent as a 'session_context' WS event so the frontend can
# display "last time you were working on X..." before the first message.

from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from core.logger import get_logger

logger = get_logger(__name__)


def _relative_date(iso_str: str) -> str:
    """Convert ISO timestamp to human-readable relative date in Spanish."""
    if not iso_str:
        return "recientemente"
    try:
        # SQLite stores as 'YYYY-MM-DD HH:MM:SS' or ISO
        ts_clean = iso_str.replace("T", " ").split(".")[0]
        dt = datetime.strptime(ts_clean, "%Y-%m-%d %H:%M:%S")
        dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - dt
        days = delta.days
        if days == 0:
            return "hoy"
        elif days == 1:
            return "ayer"
        elif days < 7:
            return f"hace {days} días"
        elif days < 30:
            weeks = days // 7
            return f"hace {weeks} semana{'s' if weeks > 1 else ''}"
        else:
            months = days // 30
            return f"hace {months} mes{'es' if months > 1 else ''}"
    except Exception:
        return "recientemente"


def _extract_topic_from_messages(messages: list[dict]) -> str:
    """
    Extract a short topic hint from the last few messages of a session.
    Looks at user messages for hardware/component keywords.
    """
    keywords_found = []
    hardware_kw = [
        "esp32", "arduino", "pico", "stm32", "esp8266",
        "relay", "motor", "sensor", "dht", "oled", "lcd",
        "mqtt", "wifi", "firmware", "circuito", "esquemático",
        "riego", "domótica", "servo", "stepper", "bmp", "mpu",
        "ds18b20", "hx711", "corriente", "tensión", "batería",
        "frecuencia", "pwm", "i2c", "spi", "uart",
    ]
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content_lower = (msg.get("content") or "").lower()
        for kw in hardware_kw:
            if kw in content_lower and kw not in keywords_found:
                keywords_found.append(kw)
        if len(keywords_found) >= 4:
            break

    return ", ".join(keywords_found[:4]) if keywords_found else ""


async def generate_session_context(
    current_session_id: str,
    sql_db,
    user_id: str = "default",
) -> dict | None:
    """
    Build a context card from the most recent past session.

    Returns None if there's no relevant past context.
    Returns a dict with:
        session_title, last_date, platform, topic_hints, message_count
    """
    try:
        # List recent sessions, excluding the current one
        sessions = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: sql_db.list_sessions(user_id=user_id, limit=10),
        )

        past_sessions = [s for s in sessions if s["id"] != current_session_id]
        if not past_sessions:
            return None

        recent = past_sessions[0]
        if not recent.get("msg_count", 0):
            # Try next session with messages
            for s in past_sessions[1:]:
                if s.get("msg_count", 0):
                    recent = s
                    break
            else:
                return None

        # Get last few messages from that session to extract topics
        messages = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: sql_db.get_conversation_by_session(
                recent["id"], limit=6, user_id=user_id
            ),
        )

        if not messages:
            return None

        topic_hints = _extract_topic_from_messages(messages)
        last_date = _relative_date(recent.get("last_msg_at") or recent.get("created_at", ""))
        title = recent.get("title") or "Conversación anterior"
        msg_count = recent.get("msg_count", len(messages))

        # Try to get platform from facts
        platform = ""
        try:
            facts = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: sql_db.get_all_facts(user_id=user_id),
            )
            platform = facts.get("platform", facts.get("session_platform", ""))
        except Exception:
            pass

        context = {
            "session_title": title,
            "last_date": last_date,
            "platform": platform,
            "topic_hints": topic_hints,
            "message_count": msg_count,
        }

        logger.info(
            f"[SessionContinuity] Context card: title={title!r} date={last_date!r} "
            f"platform={platform!r} topics={topic_hints!r}"
        )
        return context

    except Exception as e:
        logger.warning(f"[SessionContinuity] Error generando context card: {e}")
        return None
