import logging
from pathlib import Path

from fakes import FakeRedis, fake_assistant

from vectra.evaluation.cases import ANAND
from vectra.storage import RedisCache, RedisSessionStore


def test_parking_abstains_without_calling_the_llm():
    a = fake_assistant()
    r = a.ask("How do I get a parking pass for the Gurugram office?", stateless=True)
    assert r["abstained"] and r["citations"] == [] and "ticket" in r["answer"]
    assert not r["meta"]["llm_called"] and a.writer.calls == []


def test_llm_and_logs_only_ever_see_masked_text():
    a = fake_assistant()
    r = a.ask(ANAND, stateless=True)
    sent = a.writer.calls[0] + " ".join(a.retriever.queries)
    assert "9876543210" not in sent and "anand.sharma@" not in sent and "Anand" not in sent
    assert r["citations"] == ["KB-004"] and r["meta"]["pii_masked"]["EMAIL"] == 1
    log_text = Path(a.requests_log.handlers[0].baseFilename).read_text(encoding="utf-8")
    assert "9876543210" not in log_text and "anand.sharma@" not in log_text


def test_repeat_question_is_served_from_cache():
    a = fake_assistant()
    first = a.ask("My account got locked", stateless=True)
    second = a.ask("my account got   locked", stateless=True)
    assert not first["meta"]["cache_hit"] and second["meta"]["cache_hit"]
    assert len(a.writer.calls) == 1 and second["citations"] == ["KB-001"]


def test_session_followup():
    a = fake_assistant()
    first = a.ask("How do I connect to the VPN from home?")
    second = a.ask("And on Linux?", session_id=first["session_id"])
    assert second["session_id"] == first["session_id"] and second["meta"]["followup"]
    assert second["citations"] == ["KB-007"]
    assert len(a.sessions.history(first["session_id"], 10)) == 2


def test_assistant_with_redis_stores_keeps_followups_and_cache():
    now = [1000.0]
    fake = FakeRedis(lambda: now[0])
    a = fake_assistant()
    a.sessions = RedisSessionStore(fake, clock=lambda: now[0])
    a.cache = RedisCache(fake, 3600)
    first = a.ask("How do I connect to the vpn from home?")
    second = a.ask("And on Linux?", first["session_id"])
    assert second["session_id"] == first["session_id"] and second["meta"]["followup"]
    assert len(a.sessions.history(first["session_id"], 10)) == 2
    again = a.ask("How do I connect to the vpn from home?")
    assert again["meta"]["cache_hit"] and again["answer"] == first["answer"]


def test_service_error_returns_safe_json():
    a = fake_assistant()

    def boom(query):
        raise ConnectionError("pinecone down")
    a.retriever.run = boom
    logging.getLogger("vectra").disabled = True     # expected exception; keep test output clean
    try:
        r = a.ask("My account got locked", stateless=True)
    finally:
        logging.getLogger("vectra").disabled = False
    assert r["abstained"] and r["meta"]["error"] == "ConnectionError" and "ticket" in r["answer"]
