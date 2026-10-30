"""Step 4 - VerifierAgent: checks the draft against what was actually retrieved.
The draft never reaches the user unchecked."""
from __future__ import annotations

from dataclasses import dataclass

from ..privacy import scrub
from ..safety import ABSTAIN_MESSAGE, ESCALATION_EXT, ESCALATIONS, find_unsafe
from .answer import Draft
from .retrieval import Hit


@dataclass
class Verdict:
    answer: str
    citations: list[str]
    abstained: bool
    checks: dict


class VerifierAgent:
    def run(self, draft: Draft, hits: list[Hit], escalation: str | None) -> Verdict:
        retrieved = {h.doc_id for h in hits}
        checks = {"citations_dropped": [], "unsafe_blocked": [], "pii_scrubbed": False,
                  "escalation": escalation, "abstain_reason": draft.reason if draft.abstained else None}
        answer, abstained, citations = draft.answer.strip(), draft.abstained, []

        if not abstained:
            for c in draft.citations:
                c = c.strip().upper()
                if c in retrieved:
                    if c not in citations:
                        citations.append(c)
                else:
                    checks["citations_dropped"].append(c)   # cited something it wasn't given
            unsafe = find_unsafe(answer)
            if not answer:
                checks["abstain_reason"] = "empty answer"
            elif not citations:
                checks["abstain_reason"] = "no citation to a retrieved article"
            elif unsafe:
                checks["abstain_reason"] = "unsafe content blocked"
                checks["unsafe_blocked"] = unsafe
            abstained = checks["abstain_reason"] is not None

        if abstained:
            answer, citations = ABSTAIN_MESSAGE, []
        else:
            answer, checks["pii_scrubbed"] = scrub(answer)

        if escalation:
            doc_id, _, note = ESCALATIONS[escalation]
            if abstained:
                answer = f"{note} For anything else, please raise a ticket with the IT service desk."
                abstained = False
            elif ESCALATION_EXT[escalation] not in answer:   # don't say the same thing twice
                answer = f"{note}\n\n{answer}"
            if doc_id not in citations:
                citations.append(doc_id)

        return Verdict(answer, citations, abstained, checks)
