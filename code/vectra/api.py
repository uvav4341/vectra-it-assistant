"""JSON API with session management, plus the web UI.

  POST   /answer          {"question": "...", "session_id": optional} -> answer JSON
  POST   /sessions        start a session                             -> {"session_id"}
  GET    /sessions/{id}   masked history of a session
  DELETE /sessions/{id}   end a session (e.g. on logout)
  GET    /health          status, kb_version, session store
  GET    /                web UI (code/web/index.html)
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .config import MAX_QUESTION_CHARS, UI_PATH
from .pipeline import get_assistant
from .storage import RedisSessionStore, SessionStore, TTLCache


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    session_id: str | None = Field(default=None, description="Omit to start a new session")


class AnswerResponse(BaseModel):
    answer: str
    citations: list[str]
    abstained: bool
    session_id: str
    meta: dict


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_assistant().warm_up()   # create clients and open connections once, so the first user isn't slow
    yield


app = FastAPI(title="Vectra IT KB Assistant", version="1.0", lifespan=lifespan)


@app.post("/answer", response_model=AnswerResponse)
def post_answer(req: AskRequest) -> dict:
    # sync def -> FastAPI runs it in a thread pool, so slow LLM calls don't block other users
    try:
        return get_assistant().ask(req.question, req.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/sessions")
def create_session() -> dict:
    return {"session_id": get_assistant().sessions.create().id}


@app.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    session = get_assistant().sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found or expired")
    return session.to_dict()


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str) -> dict:
    return {"deleted": get_assistant().sessions.delete(session_id)}


@app.get("/", include_in_schema=False)
def ui() -> FileResponse:
    return FileResponse(UI_PATH)


@app.get("/health")
def health() -> dict:
    assistant = get_assistant()
    return {
        "status": "ok",
        "kb_version": assistant.kb_version,
        "chat_model": assistant.writer.model,
        "session_store": "redis" if isinstance(assistant.sessions, RedisSessionStore) else "memory",
        # counting keys in Redis would need a SCAN, so these are only reported for the memory store
        "active_sessions": len(assistant.sessions) if isinstance(assistant.sessions, SessionStore) else None,
        "cached_answers": len(assistant.cache) if isinstance(assistant.cache, TTLCache) else None,
    }
