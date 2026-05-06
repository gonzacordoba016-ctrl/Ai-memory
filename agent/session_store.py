# agent/session_store.py
#
# SessionStore: cache per-session de AgentState con LRU + TTL + hidratación SQL.
#
# Reemplaza el singleton global previo (un único AgentState compartido entre
# todos los chats simultáneos). Cada session_id obtiene su propia instancia,
# rehidratada desde SQL en cache miss y desalojada por inactividad o presión
# de memoria.
#
# Modelo:
#   - get(sid)     → AgentState (crea+hidrata si no existe; refresca LRU)
#   - forget(sid)  → elimina la entrada
#   - stats()      → introspección
#
# Eviction:
#   - TTL: entradas inactivas más de `ttl_seconds` se descartan.
#   - LRU: cuando se excede `max_sessions`, se descarta la más antigua.
#
# Thread-safety: RLock alrededor del OrderedDict. Operaciones O(1) amortizado.

from __future__ import annotations

import time
from collections import OrderedDict
from threading import RLock
from typing import Optional

from agent.agent_state import AgentState
from core.logger import logger


class SessionStore:
    """Per-session AgentState cache with LRU + TTL + lazy SQL hydration."""

    def __init__(
        self,
        sql_db=None,
        max_sessions: int = 100,
        ttl_seconds: int = 1800,
        history_limit: int = 20,
    ):
        self._sql_db        = sql_db
        self._max           = max_sessions
        self._ttl           = ttl_seconds
        self._history_limit = history_limit
        self._lock          = RLock()
        # OrderedDict — first key = oldest (LRU back), last = freshest (LRU front).
        self._cache: "OrderedDict[str, tuple[AgentState, float]]" = OrderedDict()

    # ── API pública ─────────────────────────────────────────────────────────

    def get(self, session_id: Optional[str]) -> AgentState:
        """Devuelve el AgentState para `session_id`. Lo crea+hidrata si es miss."""
        sid = session_id or "_default"
        now = time.time()
        with self._lock:
            self._prune_locked(now)
            if sid in self._cache:
                state, _ = self._cache.pop(sid)
                self._cache[sid] = (state, now)
                return state
            state = AgentState()
            self._hydrate(state, sid)
            self._cache[sid] = (state, now)
            self._enforce_max_locked()
            logger.info(
                f"[SessionStore] Hidratada session={sid[:8]} "
                f"(cache={len(self._cache)}/{self._max})"
            )
            return state

    def forget(self, session_id: str) -> None:
        """Elimina la entrada (p.ej. al cerrar la conversación explícitamente)."""
        with self._lock:
            if self._cache.pop(session_id, None) is not None:
                logger.info(f"[SessionStore] forget session={session_id[:8]}")

    def clear(self) -> None:
        with self._lock:
            n = len(self._cache)
            self._cache.clear()
            if n:
                logger.info(f"[SessionStore] clear() → {n} sesiones eliminadas")

    def stats(self) -> dict:
        with self._lock:
            now = time.time()
            ages = [int(now - ts) for _, ts in self._cache.values()]
            return {
                "sessions":      len(self._cache),
                "max":           self._max,
                "ttl_seconds":   self._ttl,
                "history_limit": self._history_limit,
                "oldest_age_s":  max(ages) if ages else 0,
                "newest_age_s":  min(ages) if ages else 0,
            }

    # ── Internos ────────────────────────────────────────────────────────────

    def _hydrate(self, state: AgentState, sid: str) -> None:
        """Carga últimos N mensajes y los facts persistidos desde SQL."""
        if not self._sql_db:
            return
        # Facts (perfil del usuario) — globales single-user, OK rehidratar siempre.
        try:
            facts = self._sql_db.get_all_facts() or {}
            for k, v in facts.items():
                state.set_user_fact(k, v)
        except Exception as e:
            logger.warning(f"[SessionStore] Facts hydration failed: {e}")

        if sid == "_default":
            return
        # History de la sesión.
        try:
            messages = self._sql_db.get_conversation_by_session(
                sid, limit=self._history_limit
            ) or []
            for m in messages:
                role    = m.get("role") or "user"
                content = m.get("content") or ""
                if content:
                    state.add_message(role, content)
        except Exception as e:
            logger.warning(f"[SessionStore] History hydration failed for {sid[:8]}: {e}")

    def _prune_locked(self, now: float) -> None:
        expired = [k for k, (_, ts) in self._cache.items() if now - ts > self._ttl]
        for k in expired:
            self._cache.pop(k, None)
        if expired:
            logger.info(f"[SessionStore] TTL evict: {len(expired)} session(s)")

    def _enforce_max_locked(self) -> None:
        while len(self._cache) > self._max:
            sid, _ = self._cache.popitem(last=False)
            logger.info(f"[SessionStore] LRU evict session={sid[:8]}")
