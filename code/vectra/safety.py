"""Safety rules: urgent escalations, advice that must never be given, and the fixed fallback messages."""
from __future__ import annotations

import re

ABSTAIN_MESSAGE = (
    "I couldn't find this in the Vectra IT knowledge base, so I can't give you a reliable answer. "
    "Please raise a ticket with the IT service desk and an agent will help you."
)
UNAVAILABLE_MESSAGE = (
    "The IT assistant is temporarily unavailable. Please raise a ticket with the IT service desk. "
    "If a site, warehouse or dispatch is stopped, also phone the 24x7 desk on ext. 4357."
)

# Urgent situations: (source article, trigger, note shown first). Security is checked before P1.
# The note is skipped when the answer already gives the same phone extension.
ESCALATION_EXT = {"security": "7333", "p1": "4357"}
ESCALATIONS = {
    "security": (
        "KB-006",
        re.compile(
            r"phish|suspicious (link|e-?mail|attachment)|clicked (on )?(a |the |some )?(\w+ )?(link|attachment)"
            r"|(entered|typed|gave) my password|ransom|hacked|malware|files? (are |is )?(being )?(renamed|encrypted)",
            re.IGNORECASE,
        ),
        "Security first: disconnect from the network (turn off wifi or unplug the cable, but don't shut the "
        "laptop down) and call SecOps on ext. 7333 now, then raise a Security ticket.",
    ),
    "p1": (
        "KB-003",
        re.compile(
            r"\b(all|every|whole|entire)\b[^.?!]{0,40}\b(printers?|scanners?|warehouse|site|dock|users|staff|team|office)\b"
            r"[^.?!]{0,40}\b(down|stopped|not working|can'?t work|cannot work|offline|blocked)\b"
            r"|\bdispatch (is )?(blocked|stopped|down)\b|\bdown for everyone\b|\boutage\b",
            re.IGNORECASE,
        ),
        "This sounds like a P1 (business stopped). Raise the ticket and also phone the 24x7 desk on ext. 4357.",
    ),
}

# Advice the assistant must never give, even if a retrieved article says so.
UNSAFE_UNLESS_NEGATED = [
    re.compile(r"\b(disable|turn(ing)? off|switch(ing)? off|uninstall|deactivate|stop)\b[^.]{0,40}"
               r"\b(anti-?virus|defender|endpoint protection|firewall)\b", re.IGNORECASE),
    re.compile(r"\b(share|send|tell|give)\b[^.]{0,30}\b(password|otp)\b", re.IGNORECASE),
]
UNSAFE_ALWAYS = [
    re.compile(r"vpn\.vectralogistics\.example", re.IGNORECASE),   # retired SecureLink gateway (KB-002)
]
NEGATION = re.compile(r"\b(never|do not|don't|must not|should not|shouldn't|not allowed|will never)\b", re.IGNORECASE)


def detect_escalation(text: str) -> str | None:
    for name, (_, trigger, _) in ESCALATIONS.items():
        if trigger.search(text):
            return name
    return None


def find_unsafe(text: str) -> list[str]:
    problems = [p.pattern for p in UNSAFE_ALWAYS if p.search(text)]
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        if NEGATION.search(sentence):
            continue
        problems += [m.group(0) for p in UNSAFE_UNLESS_NEGATED for m in [p.search(sentence)] if m]
    return problems
