"""Sessions and the answer cache in Redis, so every API instance (e.g. serverless) sees the same data."""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from collections import deque
from typing import Any, Callable

from ..config import (REDIS_REST_TOKEN, REDIS_REST_URL, REDIS_URL, SESSION_MAX_TURNS,
                      SESSION_TTL_SECONDS, log)
from .sessions import Session, Turn


def redis_command() -> Callable[..., Any] | None:
    """cmd(*args) -> reply for the configured Redis, or None when no Redis is configured."""
    if REDIS_URL:
        import redis
        client = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=3)
        return client.execute_command
    if REDIS_REST_URL and REDIS_REST_TOKEN:
        import httpx
        http = httpx.Client(base_url=REDIS_REST_URL, timeout=3,
                            headers={"Authorization": f"Bearer {REDIS_REST_TOKEN}"})

        def cmd(*args: Any) -> Any:
            resp = http.post("/", json=[str(a) for a in args])
            body = resp.json()
            if resp.status_code != 200 or "error" in body:
                raise RuntimeError(f"redis {args[0]} failed: {body.get('error', resp.status_code)}")
            return body["result"]
        return cmd
    return None


class RedisSessionStore:
    """SessionStore's methods, kept in Redis.
    One JSON value per session; every read or write pushes the expiry forward (sliding TTL).
    Redis evicts by TTL, so there is no MAX_SESSIONS bound here. Two requests appending to the
    SAME session at the same moment can lose one turn (read-modify-write) - fine for a chat UI."""

    def __init__(self, cmd: Callable[..., Any], ttl_seconds: int = SESSION_TTL_SECONDS,
                 max_turns: int = SESSION_MAX_TURNS, clock: Callable[[], float] = time.time,
                 prefix: str = "vectra:session:"):
        self._cmd = cmd
        self.ttl = ttl_seconds
        self.max_turns = max_turns
        self._clock = clock
        self.prefix = prefix

    def _save(self, session: Session) -> None:
        self._cmd("SET", self.prefix + session.id, json.dumps(session.to_dict()), "EX", self.ttl)

    def create(self) -> Session:
        now = self._clock()
        session = Session(secrets.token_urlsafe(16), now, now, deque(maxlen=self.max_turns))
        self._save(session)
        return session

    def get(self, session_id: str) -> Session | None:
        raw = self._cmd("GETEX", self.prefix + session_id, "EX", self.ttl)   # read + refresh TTL
        if raw is None:
            return None
        data = json.loads(raw)
        turns = deque((Turn(**t) for t in data["turns"]), maxlen=self.max_turns)
        return Session(data["session_id"], data["created_at"], self._clock(), turns)

    def get_or_create(self, session_id: str | None) -> tuple[Session, bool]:
        session = self.get(session_id) if session_id else None
        return (session, False) if session else (self.create(), True)

    def append(self, session_id: str, turn: Turn) -> None:
        session = self.get(session_id)
        if session is not None:
            session.turns.append(turn)
            self._save(session)

    def history(self, session_id: str, n: int) -> list[Turn]:
        session = self.get(session_id)
        return list(session.turns)[-n:] if session and n > 0 else []

    def delete(self, session_id: str) -> bool:
        return bool(self._cmd("DEL", self.prefix + session_id))

    def warm_up(self) -> None:
        self._cmd("PING")


class RedisCache:
    """TTLCache's get/set in Redis. Values must be JSON. A Redis error is treated as a cache miss:
    the cache only makes answers faster, it must never make them fail."""

    def __init__(self, cmd: Callable[..., Any], ttl_seconds: int, prefix: str = "vectra:answer:"):
        self._cmd = cmd
        self.ttl = ttl_seconds
        self.prefix = prefix

    def _key(self, key: str) -> str:
        return self.prefix + hashlib.sha256(key.encode()).hexdigest()

    def get(self, key: str) -> Any | None:
        try:
            raw = self._cmd("GET", self._key(key))
            return json.loads(raw) if raw else None
        except Exception:
            log.warning("answer cache read failed", exc_info=True)
            return None

    def set(self, key: str, value: Any) -> None:
        try:
            self._cmd("SET", self._key(key), json.dumps(value), "EX", self.ttl)
        except Exception:
            log.warning("answer cache write failed", exc_info=True)
