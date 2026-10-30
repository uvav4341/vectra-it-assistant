"""Evaluation: the brief's 5 samples + tricky cases from the KB, each part scored separately
(retrieval, abstain, citation, content, safety, latency). Every question runs twice (cold, then
warm from cache). Writes reports/eval_results.json + eval_report.md."""
from .runner import run_eval

__all__ = ["run_eval"]
