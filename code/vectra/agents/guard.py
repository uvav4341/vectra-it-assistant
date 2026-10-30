"""Step 1 - GuardAgent: cleans the question, masks personal data and spots urgent situations."""
from __future__ import annotations

from dataclasses import dataclass

from ..config import MAX_QUESTION_CHARS
from ..privacy import mask
from ..safety import detect_escalation


@dataclass
class GuardResult:
    question: str                 # masked; the raw question never leaves this agent
    pii: dict[str, int]
    escalation: str | None


class GuardAgent:
    def run(self, question: str) -> GuardResult:
        q = " ".join((question or "").split())[:MAX_QUESTION_CHARS]
        if not q:
            raise ValueError("question is empty")
        masked = mask(q)
        return GuardResult(masked.text, masked.found, detect_escalation(masked.text))
