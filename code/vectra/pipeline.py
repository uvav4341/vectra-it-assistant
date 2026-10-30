"""The pipeline: runs the four agents in order with sessions, follow-ups, caching and logging.

    question -> Guard -> (session, follow-up, cache) -> Retrieval -> Answer -> Verifier -> JSON
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict
from pathlib import Path

from .agents import AnswerAgent, Draft, GuardAgent, RetrievalAgent, Verdict, VerifierAgent
from .config import (ANSWER_CACHE_SIZE, ANSWER_CACHE_TTL_SECONDS, CHAT_MODEL, LLM_TIMEOUT_SECONDS,
                     LOG_PATH, MIN_SCORE, OPENAI_API_KEY, PINECONE_API_KEY, PINECONE_INDEX,
                     SESSION_HISTORY_FOR_LLM, TOP_K, log, ms)
from .followup import build_query
from .knowledge_base import read_kb_version
from .request_log import request_logger
from .safety import UNAVAILABLE_MESSAGE
from .storage import RedisCache, RedisSessionStore, SessionStore, TTLCache, Turn, redis_command


class Assistant:
    def __init__(self, *, openai_client=None, index=None, retriever=None, writer=None,
                 sessions: SessionStore | RedisSessionStore | None = None, chat_model: str | None = None,
                 top_k: int | None = None, min_score: float | None = None, use_cache: bool = True,
                 cache: TTLCache | RedisCache | None = None, log_path: Path = LOG_PATH):
        if retriever is None or writer is None:
            if openai_client is None:
                from openai import OpenAI
                openai_client = OpenAI(api_key=OPENAI_API_KEY, timeout=LLM_TIMEOUT_SECONDS, max_retries=2)
            if index is None and retriever is None:
                from pinecone import Pinecone
                index = Pinecone(api_key=PINECONE_API_KEY).Index(PINECONE_INDEX)
        self.guard = GuardAgent()
        self.retriever = retriever or RetrievalAgent(openai_client, index, top_k=top_k or TOP_K,
                                                     min_score=MIN_SCORE if min_score is None else min_score)
        self.writer = writer or AnswerAgent(openai_client, model=chat_model or CHAT_MODEL)
        self.verifier = VerifierAgent()
        self.sessions = sessions or SessionStore()
        self.cache = (cache or TTLCache(ANSWER_CACHE_SIZE, ANSWER_CACHE_TTL_SECONDS)) if use_cache else None
        self.kb_version = read_kb_version()
        self.requests_log = request_logger(Path(log_path))

    def warm_up(self) -> None:
        for part in (self.retriever, self.sessions):
            if hasattr(part, "warm_up"):
                try:
                    part.warm_up()
                except Exception:  # a failed warm-up must not stop startup; ask() still handles errors
                    log.warning("warm-up failed", exc_info=True)

    def ask(self, question: str, session_id: str | None = None, stateless: bool = False) -> dict:
        t_total = time.perf_counter()
        timings: dict[str, float] = {}

        # 1. Guard: mask personal data, detect urgency
        t = time.perf_counter()
        guard = self.guard.run(question)          # raises ValueError on an empty question
        timings["guard_ms"] = ms(t)

        # 2. Session + follow-up: a short follow-up is searched with the question that set the topic
        session, created = (None, False) if stateless else self.sessions.get_or_create(session_id)
        history = list(session.turns)[-SESSION_HISTORY_FOR_LLM:] if session else []   # already loaded
        query, followup = build_query(guard.question, list(session.turns) if session else [])

        # 3. Cache: follow-ups depend on the conversation, so only stand-alone questions are cached
        model = getattr(self.writer, "model", "")
        cache_key = None if followup else f"{self.kb_version}|{model}|{query.lower()}"
        cached = self.cache.get(cache_key) if (self.cache is not None and cache_key) else None

        llm_called, error = False, None
        if cached:
            verdict, retrieved = Verdict(**cached["verdict"]), cached["retrieved"]
        else:
            try:
                # 4. Retrieval
                retrieval = self.retriever.run(query)
                timings.update(retrieval.timings)
                retrieved = [{"doc_id": h.doc_id, "score": round(h.score, 3)} for h in retrieval.hits]

                # 5. Answer - only when something relevant was found
                if retrieval.relevant:
                    t = time.perf_counter()
                    draft = self.writer.run(guard.question, retrieval.relevant, history)
                    timings["answer_ms"] = ms(t)
                    llm_called = True
                else:
                    # Nothing relevant -> abstain without paying for (or waiting on) an LLM call.
                    draft = Draft("", [], True, "no KB article above similarity threshold")

                # 6. Verifier
                t = time.perf_counter()
                verdict = self.verifier.run(draft, retrieval.relevant, guard.escalation)
                timings["verify_ms"] = ms(t)

                if self.cache is not None and cache_key:
                    self.cache.set(cache_key, {"verdict": asdict(verdict), "retrieved": retrieved})
            except Exception as exc:  # OpenAI/Pinecone down, timeout, ... -> safe fallback, never a crash
                log.exception("answer pipeline failed")
                error = type(exc).__name__
                retrieved = []
                verdict = Verdict(UNAVAILABLE_MESSAGE, [], True, {"abstain_reason": "service error"})

        if session and not error:
            self.sessions.append(session.id, Turn(guard.question, verdict.answer, verdict.citations,
                                                  verdict.abstained, time.time()))
        timings["total_ms"] = ms(t_total)

        meta = {
            "session_new": created,
            "followup": followup,
            "cache_hit": bool(cached),
            "llm_called": llm_called,
            "retrieved": retrieved,
            "pii_masked": guard.pii,
            "checks": verdict.checks,
            "latency_ms": timings,
            "kb_version": self.kb_version,
            "error": error,
        }
        self.requests_log.info(json.dumps({
            "ts": round(time.time(), 3),
            "session_id": session.id if session else None,
            "question_masked": guard.question,
            "citations": verdict.citations,
            "abstained": verdict.abstained,
            **{k: meta[k] for k in ("cache_hit", "llm_called", "retrieved", "pii_masked", "latency_ms", "error")},
        }, ensure_ascii=False))

        return {
            "answer": verdict.answer,
            "citations": verdict.citations,
            "abstained": verdict.abstained,
            "session_id": session.id if session else None,
            "meta": meta,
        }


_assistant: Assistant | None = None
_assistant_lock = threading.Lock()


def get_assistant() -> Assistant:
    """One shared Assistant per process: clients, caches and sessions stay warm."""
    global _assistant
    with _assistant_lock:
        if _assistant is None:
            cmd = redis_command()
            if cmd:
                _assistant = Assistant(sessions=RedisSessionStore(cmd),
                                       cache=RedisCache(cmd, ANSWER_CACHE_TTL_SECONDS))
            else:
                _assistant = Assistant()
        return _assistant


def answer(question: str) -> dict:
    """The function the brief asks for."""
    r = get_assistant().ask(question, stateless=True)
    return {"answer": r["answer"], "citations": r["citations"], "abstained": r["abstained"]}
