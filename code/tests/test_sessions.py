from fakes import FakeClock, FakeRedis

from vectra.followup import build_query
from vectra.storage import RedisSessionStore, SessionStore, Turn


def test_session_sliding_ttl():
    clock = FakeClock()
    store = SessionStore(ttl_seconds=60, clock=clock)
    s = store.create()
    clock.t += 50
    assert store.get(s.id) is not None      # touched -> TTL restarts
    clock.t += 50
    assert store.get(s.id) is not None
    clock.t += 61
    assert store.get(s.id) is None          # idle too long


def test_unknown_session_id_gets_a_new_id():
    s, created = SessionStore().get_or_create("made-up-id")
    assert created and s.id != "made-up-id"


def test_history_is_bounded_and_eviction_works():
    store = SessionStore(max_turns=3, max_sessions=2)
    s = store.create()
    for i in range(5):
        store.append(s.id, Turn(f"q{i}", "a", [], False, 0))
    assert [t.question for t in store.history(s.id, 10)] == ["q2", "q3", "q4"]
    store.create()
    store.create()                          # 3rd session evicts the least recently used
    assert len(store) == 2 and store.get(s.id) is None


def test_followup_query_uses_previous_question():
    hist = [Turn("How do I connect to the VPN from home?", "...", ["KB-007"], False, 0)]
    q, followup = build_query("And on Linux?", hist)
    assert followup and "VPN" in q
    long_q = "What is the resolution target for a P2 ticket in the Mumbai warehouse?"
    assert build_query(long_q, hist) == (long_q, False)
    # short but a new topic: searched on its own
    assert build_query("ZenTunnel shows ZT-401", hist) == ("ZenTunnel shows ZT-401", False)
    assert build_query("Does it work on Mac?", hist)[1]
    # a chain of follow-ups keeps the original topic
    chain = hist + [Turn("And on Linux?", "...", ["KB-007"], False, 1)]
    q, followup = build_query("What about macOS?", chain)
    assert followup and q.startswith("How do I connect to the VPN") and "Linux" not in q


def test_redis_session_store_matches_memory_store():
    now = [1000.0]
    store = RedisSessionStore(FakeRedis(lambda: now[0]), ttl_seconds=60, max_turns=2,
                              clock=lambda: now[0])
    s = store.create()
    for i in range(3):
        store.append(s.id, Turn(f"q{i}", "a", [], False, now[0]))
    assert [t.question for t in store.history(s.id, 10)] == ["q1", "q2"]     # bounded
    now[0] += 50
    assert store.get(s.id) is not None                                        # sliding TTL
    now[0] += 50
    assert store.get(s.id) is not None
    now[0] += 61
    assert store.get(s.id) is None                                            # expired
    other, created = store.get_or_create("made-up-id")
    assert created and other.id != "made-up-id"
    assert store.delete(other.id) and store.get(other.id) is None
