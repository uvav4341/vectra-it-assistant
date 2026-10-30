"""PII masking - runs before anything is embedded, sent to OpenAI, logged or stored."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

PII_PATTERNS = [
    # full address, or a cut-off one ("anand.sharma@...") - the part before @ already identifies the person
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@(?:[A-Za-z0-9.-]+\.[A-Za-z]{2,})?")),
    # Indian mobile: optional +91 / 91, then 10 digits starting 6-9 (spaces/dashes allowed)
    ("PHONE", re.compile(r"(?<![\w+])(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\w)")),
    # Any other international number written with a leading +
    ("PHONE", re.compile(r"(?<![\w+])\+\d{1,3}[\s-]?\d[\d\s-]{6,}\d(?!\w)")),
    ("EMPLOYEE_ID", re.compile(r"\bVX\d{5}\b", re.IGNORECASE)),
]
# "I'm Anand Sharma", "my name is Priya" -> keep the intro words, mask the name
NAME_INTRO = re.compile(r"\b((?i:i['’]m|i am|my name is))\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})")
PLACEHOLDER = re.compile(r"\s*\[(EMAIL|PHONE|EMPLOYEE_ID|NAME)\]")


@dataclass
class Masked:
    text: str
    found: dict[str, int] = field(default_factory=dict)


def mask(text: str) -> Masked:
    found: dict[str, int] = {}

    def count(label: str) -> None:
        found[label] = found.get(label, 0) + 1

    def replace_name(m: re.Match) -> str:
        count("NAME")
        return f"{m.group(1)} [NAME]"

    text = NAME_INTRO.sub(replace_name, text)
    for label, pattern in PII_PATTERNS:
        def replace(m: re.Match, label=label) -> str:
            count(label)
            return f"[{label}]"
        text = pattern.sub(replace, text)
    return Masked(text, found)


def scrub(answer: str) -> tuple[str, bool]:
    """Remove personal data (or its placeholders) from a reply so it is never echoed back."""
    cleaned = PLACEHOLDER.sub("", mask(answer).text)
    cleaned = re.sub(r"\s+([,.!?])", r"\1", cleaned).strip()
    return cleaned, cleaned != answer.strip()
