"""Runs every case against the live pipeline (cold, then warm from cache) for each model."""
from __future__ import annotations

from ..config import REPORT_DIR
from ..pipeline import Assistant
from .cases import EVAL_CASES, EVAL_SESSION_CASES
from .report import write_report
from .scoring import eval_row, summarise


def run_suite(assistant: Assistant, label: str) -> list[dict]:
    rows = [eval_row(case, assistant.ask(case["q"], stateless=True), label) for case in EVAL_CASES]
    for convo in EVAL_SESSION_CASES:
        sid = None
        for case in convo:
            resp = assistant.ask(case["q"], session_id=sid)
            sid = resp["session_id"]
            rows.append(eval_row(case, resp, label))
    return rows


def run_eval(models: list[str]) -> int:
    runs, version = [], "unknown"
    for model in models:
        assistant = Assistant(chat_model=model)
        version = assistant.kb_version
        for label in ("cold", "warm"):
            rows = run_suite(assistant, label)
            summary = summarise(rows)
            runs.append({"model": model, "pass": label, "summary": summary, "rows": rows})
            print(f"{model:<16} {label:<5} " + "  ".join(f"{k}={v}" for k, v in summary.items()
                                                       if not k.startswith("avg_")))
    write_report(runs, version)
    print(f"\nWrote {REPORT_DIR / 'eval_results.json'} and {REPORT_DIR / 'eval_report.md'}")
    unsafe = any(r["scores"]["safe"] is False for run in runs for r in run["rows"])
    return 1 if unsafe else 0       # non-zero exit if anything unsafe got through
