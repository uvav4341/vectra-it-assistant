"""Step 2 - RetrievalAgent: embeds the question and finds the current KB articles about it in Pinecone."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from functools import lru_cache

from ..config import EMBED_MODEL, MIN_SCORE, TOP_K, ms


@dataclass
class Hit:
    doc_id: str
    title: str
    score: float
    text: str
    effective_date: str


@dataclass
class RetrievalResult:
    hits: list[Hit]               # everything Pinecone returned (for logs / eval)
    relevant: list[Hit]           # hits above the similarity threshold
    timings: dict[str, float] = field(default_factory=dict)


class RetrievalAgent:
    def __init__(self, openai_client, index, top_k: int = TOP_K, min_score: float = MIN_SCORE,
                 embed_model: str = EMBED_MODEL):
        self.client = openai_client
        self.index = index
        self.top_k = top_k
        self.min_score = min_score
        self.embed_model = embed_model
        # Repeat questions skip the embedding call entirely.
        self._embed = lru_cache(maxsize=4096)(self._embed_uncached)

    def warm_up(self) -> None:
        """Open the HTTPS connections to OpenAI and Pinecone before the first user asks.
        Cold, the first question took ~6 s (TLS + Pinecone host lookup); warm it takes ~2 s."""
        self._embed("warm up")
        self.index.describe_index_stats()

    def _embed_uncached(self, text: str) -> tuple[float, ...]:
        resp = self.client.embeddings.create(model=self.embed_model, input=text)
        return tuple(resp.data[0].embedding)

    def run(self, query: str) -> RetrievalResult:
        t = time.perf_counter()
        vector = self._embed(" ".join(query.split()))
        embed_ms = ms(t)

        t = time.perf_counter()
        res = self.index.query(
            vector=list(vector),
            top_k=self.top_k,
            filter={"status": {"$eq": "current"}},   # 2nd safety net: deprecated/unverified never come back
            include_metadata=True,
        )
        search_ms = ms(t)

        hits = [Hit(doc_id=m.metadata["doc_id"], title=m.metadata.get("title", ""), score=float(m.score),
                    text=m.metadata.get("text", ""), effective_date=m.metadata.get("effective_date", ""))
                for m in res.matches]
        relevant = [h for h in hits if h.score >= self.min_score]
        return RetrievalResult(hits, relevant, {"embed_ms": embed_ms, "search_ms": search_ms})
