"""Writes reports/eval_results.json (everything) and reports/eval_report.md (readable summary)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..config import REPORT_DIR
from .cases import EVAL_CASES, EVAL_SESSION_CASES


def write_report(runs: list[dict], version: str, report_dir: Path = REPORT_DIR) -> None:
    report_dir.mkdir(exist_ok=True)
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (report_dir / "eval_results.json").write_text(
        json.dumps({"generated_at": generated, "kb_version": version, "runs": runs}, indent=2, ensure_ascii=False),
        encoding="utf-8")

    n = len(EVAL_CASES) + sum(map(len, EVAL_SESSION_CASES))
    lines = [f"# Eval report\n\nGenerated {generated} - kb_version `{version}` - {n} questions per pass\n",
             "| model | pass | retrieval | abstain | citation | content | safe | p50 ms | p95 ms | LLM calls | cache hits |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for run in runs:
        s = run["summary"]
        lines.append(f"| {run['model']} | {run['pass']} | {s['retrieval']} | {s['abstain']} | {s['citation']} | "
                     f"{s['content']} | {s['safe']} | {s['p50_ms']} | {s['p95_ms']} | {s['llm_calls']} | {s['cache_hits']} |")
    lines.append("\nAverage stage latency (cold pass): " + ", ".join(
        f"{run['model']}: embed {run['summary']['avg_embed_ms']} / search {run['summary']['avg_search_ms']} / "
        f"LLM {run['summary']['avg_answer_ms']} ms" for run in runs if run["pass"] == "cold"))

    lines.append("\n## Answers (cold pass, first model)\n")
    first = next(run for run in runs if run["pass"] == "cold")
    for r in first["rows"]:
        bad = [k for k, v in r["scores"].items() if v is False]
        lines.append(f"**{r['id']}** {'FAIL ' + ', '.join(bad) if bad else 'ok'} - "
                     f"cited {r['response']['citations']} abstained={r['response']['abstained']} "
                     f"retrieved {[(x['doc_id'], x['score']) for x in r['meta']['retrieved']]}\n")
        lines.append(f"> Q: {r['question_masked']}\n>\n> A: {r['response']['answer']}\n")
    (report_dir / "eval_report.md").write_text("\n".join(lines), encoding="utf-8")
