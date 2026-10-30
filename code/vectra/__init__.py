"""Vectra Logistics IT KB assistant.

answer(question) -> {"answer": str, "citations": [str], "abstained": bool}
Answers only from the Vectra IT KB, cites the articles used, abstains (and suggests a ticket)
when the KB doesn't cover the question, and masks personal data before anything leaves the process.
"""
from .pipeline import Assistant, answer, get_assistant

__all__ = ["answer", "Assistant", "get_assistant"]
