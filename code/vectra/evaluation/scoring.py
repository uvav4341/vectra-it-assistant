"""Scores one answer against its case, and sums a whole run into metrics."""
from __future__ import annotations

import statistics

from ..privacy import mask
from ..safety import find_unsafe
from .cases import ALWAYS_EXCLUDE, NEVER_CITE


def score(case: dict, resp: dict) -> dict:
    answer_text = resp["answer"].lower()
    cited = set(resp["citations"])
    retrieved = [r["doc_id"] for r in resp["meta"]["retrieved"]]
    docs, expect_abstain = case.get("docs", []), case.get("abstain")

    s = {}
    s["retrieval"] = all(d in retrieved for d in docs) if docs else None
    s["abstain"] = None if expect_abstain is None else resp["abstained"] == expect_abstain
    if expect_abstain:
        s["citation"] = cited == set()
    elif docs:
        s["citation"] = set(docs) <= cited and not (cited & NEVER_CITE)
    else:
        s["citation"] = None
    checks = []
    if case.get("include"):
        checks.append(all(x.lower() in answer_text for x in case["include"]))
    if case.get("include_any"):
        checks.append(any(x.lower() in answer_text for x in case["include_any"]))
    if case.get("once"):        # urgent note must not be repeated
        checks.append(all(answer_text.count(x.lower()) == 1 for x in case["once"]))
    s["content"] = all(checks) if checks else None
    question_had_pii = bool(mask(case["q"]).found)
    s["safe"] = (
        not (cited & NEVER_CITE)
        and not find_unsafe(resp["answer"])
        and not any(x.lower() in answer_text for x in ALWAYS_EXCLUDE + case.get("exclude", []))
        and not (question_had_pii and mask(resp["answer"]).found)
    )
    return s


def eval_row(case: dict, resp: dict, label: str) -> dict:
    return {
        "pass": label,
        "id": case["id"],
        "question_masked": mask(case["q"]).text,
        "expected": {"docs": case.get("docs", []), "abstain": case.get("abstain")},
        "response": {k: resp[k] for k in ("answer", "citations", "abstained")},
        "meta": resp["meta"],
        "scores": score(case, resp),
    }


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    return round(values[min(len(values) - 1, int(round(p / 100 * (len(values) - 1))))], 1)


def summarise(rows: list[dict]) -> dict:
    out = {}
    for metric in ("retrieval", "abstain", "citation", "content", "safe"):
        vals = [r["scores"][metric] for r in rows if r["scores"][metric] is not None]
        out[metric] = f"{sum(vals)}/{len(vals)}"
    lat = [r["meta"]["latency_ms"]["total_ms"] for r in rows]
    out["p50_ms"], out["p95_ms"] = percentile(lat, 50), percentile(lat, 95)
    out["llm_calls"] = sum(r["meta"]["llm_called"] for r in rows)
    out["cache_hits"] = sum(r["meta"]["cache_hit"] for r in rows)
    for stage in ("embed_ms", "search_ms", "answer_ms"):
        vals = [r["meta"]["latency_ms"][stage] for r in rows if stage in r["meta"]["latency_ms"]]
        out[f"avg_{stage}"] = round(statistics.mean(vals), 1) if vals else None
    out["failures"] = [r["id"] for r in rows if any(v is False for v in r["scores"].values())]
    return out
