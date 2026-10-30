"""In-memory chat sessions.

- Session ids are random; an unknown or expired id gets a NEW id (can't pick or hijack one).
- Only masked text is stored. Every operation is O(1) under one lock (microseconds).
- For more than one API instance, redis_store.RedisSessionStore keeps the same methods in Redis.
"""
from __future__ import annotations

import secrets
import threading
import time
from collections import OrderedDict, deque
from dataclasses import asdict, dataclass, field
from typing import Callable

from ..config import MAX_SESSIONS, SESSION_MAX_TURNS, SESSION_TTL_SECONDS


@dataclass
class Turn:
    question: str          # masked
    answer: str
    citations: list[str]
    abstained: bool
    ts: float


@dataclass
class Session:
    id: str
    created_at: float
    last_seen: float
    turns: deque = field(default_factory=deque)

    def to_dict(self) -> dict:
        return {"session_id": self.id, "created_at": self.created_at, "last_seen": self.last_seen,
                "turns": [asdict(t) for t in self.turns]}


class SessionStore:
    """Sliding TTL, bounded history per session, LRU eviction, thread-safe."""

    def __init__(self, ttl_seconds: int = SESSION_TTL_SECONDS, max_turns: int = SESSION_MAX_TURNS,
                 max_sessions: int = MAX_SESSIONS, clock: Callable[[], float] = time.time):
        self.ttl = ttl_seconds
        self.max_turns = max_turns
        self.max_sessions = max_sessions
        self._clock = clock
        # Ordered oldest -> most recently used, so expiry/eviction only looks at the front.
        self._sessions: OrderedDict[str, Session] = OrderedDict()
        self._lock = threading.Lock()

    def create(self) -> Session:
        with self._lock:
            now = self._clock()
            self._evict(now)
            session = Session(secrets.token_urlsafe(16), now, now, deque(maxlen=self.max_turns))
            self._sessions[session.id] = session
            return session

    def get(self, session_id: str) -> Session | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            now = self._clock()
            if now - session.last_seen > self.ttl:
                del self._sessions[session_id]
                return None
            session.last_seen = now
            self._sessions.move_to_end(session_id)
            return session

    def get_or_create(self, session_id: str | None) -> tuple[Session, bool]:
        """Returns (session, created)."""
        session = self.get(session_id) if session_id else None
        return (session, False) if session else (self.create(), True)

    def append(self, session_id: str, turn: Turn) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                session.turns.append(turn)
                session.last_seen = self._clock()
                self._sessions.move_to_end(session_id)

    def history(self, session_id: str, n: int) -> list[Turn]:
        """Copy of the last n turns (safe to use outside the lock)."""
        with self._lock:
            session = self._sessions.get(session_id)
            return list(session.turns)[-n:] if session and n > 0 else []

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)

    def _evict(self, now: float) -> None:
        # caller holds the lock
        while self._sessions:
            oldest = next(iter(self._sessions.values()))
            if now - oldest.last_seen > self.ttl or len(self._sessions) >= self.max_sessions:
                self._sessions.popitem(last=False)
            else:
                break
