"""Reads the KB articles and decides which ones are safe to ingest.

Split strategy: ONE ARTICLE = ONE VECTOR. Every article is under 1.5 KB, so splitting gains nothing
and risks cutting the KB-003 priority table or the KB-007 error-code table in half. A whole article
is also exactly the unit we cite.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .config import KB_DIR, MANIFEST_PATH

REQUIRED_FIELDS = ("doc_id", "title", "status", "effective_date")

# Text written to an AI instead of to staff. KB-099 contains this; a reviewed IT article never should.
INJECTION_PATTERN = re.compile(
    r"(note|instruction)s? for (ai|llm|chatbot)|\bai assistants?\b|ignore (all |any )?(previous|prior) instructions"
    r"|system prompt",
    re.IGNORECASE,
)


@dataclass
class Article:
    doc_id: str
    title: str
    status: str
    effective_date: str
    body: str
    path: Path
    meta: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        """What gets embedded and shown to the LLM."""
        return f"{self.title}\n\n{self.body}"


def parse_article(path: Path) -> Article:
    raw = Path(path).read_text(encoding="utf-8")
    if not raw.startswith("---"):
        raise ValueError(f"{Path(path).name}: missing front matter")
    # maxsplit=2 keeps the "| --- |" rows of markdown tables inside the body
    _, front, body = raw.split("---", 2)
    meta = {k: str(v) for k, v in (yaml.safe_load(front) or {}).items()}
    missing = [k for k in REQUIRED_FIELDS if k not in meta]
    if missing:
        raise ValueError(f"{Path(path).name}: missing {missing}")
    return Article(meta["doc_id"], meta["title"], meta["status"].lower(), meta["effective_date"],
                   body.strip(), Path(path), meta)


def load_articles(kb_dir: Path = KB_DIR) -> list[Article]:
    return sorted((parse_article(p) for p in Path(kb_dir).glob("KB-*.md")), key=lambda a: a.doc_id)


def ingest_decision(article: Article) -> tuple[bool, str]:
    """Only reviewed, current articles go into the index. Returns (ingest?, reason)."""
    reasons = []
    if article.status == "deprecated":
        reasons.append(f"deprecated, superseded by {article.meta.get('superseded_by', 'unknown')}")
    elif article.status != "current":
        reasons.append(f"status '{article.status}' (not reviewed by IT)")
    if INJECTION_PATTERN.search(article.body):
        reasons.append("contains instructions aimed at AI assistants (prompt injection)")
    return (False, "; ".join(reasons)) if reasons else (True, "current")


def kb_version(articles: list[Article]) -> str:
    """Hash of what is in the index. Changes whenever an article or its status changes,
    which automatically invalidates the answer cache."""
    h = hashlib.sha256()
    for a in sorted(articles, key=lambda a: a.doc_id):
        h.update(f"{a.doc_id}|{a.status}|{a.effective_date}|{a.text}".encode("utf-8"))
    return h.hexdigest()[:12]


def read_kb_version() -> str:
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["kb_version"]
    except (OSError, ValueError, KeyError):
        return "unknown"
