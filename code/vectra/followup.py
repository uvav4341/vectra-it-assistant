"""Follow-up detection: decides what text to search with when a question depends on the last one."""
from __future__ import annotations

import re

from .storage.sessions import Turn

# Follow-ups ("And on Linux?", "does it work on Mac?") start with a linking word or point back with
# a pronoun. Length alone is not enough: "ZenTunnel shows ZT-401" is short but a new topic, and
# gluing it to the previous question would search for the wrong article.
FOLLOWUP = re.compile(r"^(and|also|what about|how about|what if|same for|then|but)\b"
                      r"|\b(it|that|this|those|them|there)\b", re.IGNORECASE)


def is_followup(question: str) -> bool:
    words = len(question.split())
    return words <= 2 or (words <= 12 and bool(FOLLOWUP.search(question)))   # "On Linux?" has no linking word


def build_query(question: str, history: list[Turn]) -> tuple[str, bool]:
    """Text to search with. A follow-up is searched together with the question that set the topic.
    Chains go back past earlier follow-ups: VPN address -> "And on Linux?" -> "What about macOS?"
    searches "VPN address ... What about macOS?", not "And on Linux? What about macOS?"."""
    if not history or not is_followup(question):
        return question, False
    topic = next((t.question for t in reversed(history) if not is_followup(t.question)), history[0].question)
    return f"{topic} {question}", True
