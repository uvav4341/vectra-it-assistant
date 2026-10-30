"""Stand-ins for OpenAI, Pinecone, Redis and the clock, so the tests make no network calls."""
import tempfile
from pathlib import Path

from vectra.agents import Draft, Hit, RetrievalResult
from vectra.pipeline import Assistant


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class FakeRetriever:
    """Returns preset hits when a keyword appears in the query."""

    def __init__(self, hits_by_word):
        self.hits_by_word = hits_by_word
        self.queries = []

    def run(self, query):
        self.queries.append(query)
        for word, hits in self.hits_by_word.items():
            if word in query.lower():
                return RetrievalResult(hits, hits, {"embed_ms": 0.0, "search_ms": 0.0})
        return RetrievalResult([], [], {"embed_ms": 0.0, "search_ms": 0.0})


class FakeWriter:
    model = "fake"

    def __init__(self):
        self.calls = []

    def run(self, question, hits, history):
        self.calls.append(question)
        return Draft(f"Answer from {hits[0].doc_id}.", [hits[0].doc_id], False)


class FakeRedis:
    """The few Redis commands the stores use, with expiry on a fake clock."""

    def __init__(self, clock):
        self.clock, self.data = clock, {}

    def __call__(self, op, *args):
        live = {k: v for k, v in self.data.items() if v[1] > self.clock()}
        self.data = live
        if op == "PING":
            return "PONG"
        if op == "SET":                               # SET key value EX seconds
            self.data[args[0]] = (args[1], self.clock() + int(args[3]))
            return "OK"
        if op == "GET":
            return live[args[0]][0] if args[0] in live else None
        if op == "GETEX":                             # GETEX key EX seconds
            if args[0] not in live:
                return None
            self.data[args[0]] = (live[args[0]][0], self.clock() + int(args[2]))
            return live[args[0]][0]
        if op == "DEL":
            return int(self.data.pop(args[0], None) is not None)
        raise AssertionError(op)


def fake_assistant() -> Assistant:
    retriever = FakeRetriever({
        "locked": [Hit("KB-001", "Password", 0.7, "...", "")],
        "mail": [Hit("KB-004", "Email", 0.6, "...", "")],
        "vpn": [Hit("KB-007", "ZenTunnel", 0.6, "...", "")],
    })
    log_path = Path(tempfile.mkdtemp()) / "requests.jsonl"
    return Assistant(retriever=retriever, writer=FakeWriter(), log_path=log_path)
