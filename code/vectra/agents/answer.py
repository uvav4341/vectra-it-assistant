"""Step 3 - AnswerAgent: the only LLM call. Drafts a JSON answer from the retrieved articles only."""
from __future__ import annotations

import json
from dataclasses import dataclass

from ..config import CHAT_MODEL, LLM_MAX_TOKENS
from ..storage.sessions import Turn
from .prompts import SYSTEM_PROMPT, build_user_message
from .retrieval import Hit


@dataclass
class Draft:
    answer: str
    citations: list[str]
    abstained: bool
    reason: str | None = None

    @classmethod
    def from_json(cls, content: str) -> "Draft":
        try:
            data = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            return cls("", [], True, "model returned invalid JSON")
        citations = data.get("citations") or []
        if not isinstance(citations, list):
            citations = [citations]
        abstained = data.get("abstained") in (True, "true", "True")
        return cls(str(data.get("answer") or ""), [str(c) for c in citations], abstained,
                   "model abstained" if abstained else None)


class AnswerAgent:
    def __init__(self, openai_client, model: str = CHAT_MODEL):
        self.client = openai_client
        self.model = model

    def run(self, question: str, hits: list[Hit], history: list[Turn]) -> Draft:
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            max_tokens=LLM_MAX_TOKENS,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_message(question, hits, history)},
            ],
        )
        return Draft.from_json(resp.choices[0].message.content)
