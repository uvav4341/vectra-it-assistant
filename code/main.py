"""Vectra IT KB assistant - command line.

    python main.py ingest --dry-run   which articles go in and why (no API calls)
    python main.py ingest             embed + upsert to Pinecone
    python main.py ask "question"     one answer as JSON
    python main.py chat               interactive chat in one session
    python main.py eval               scored test run -> reports/
    python main.py serve              web UI + JSON API on http://localhost:8000 (docs at /docs)
    python main.py test               offline tests (no API calls)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from vectra.config import CHAT_MODEL


def chat() -> None:
    from vectra.pipeline import get_assistant
    print("Connecting...")
    assistant, sid = get_assistant(), None
    assistant.warm_up()
    print("Vectra IT assistant - type a question, empty line to quit.")
    while (q := input("\nyou> ").strip()):
        r = assistant.ask(q, sid)
        sid = r["session_id"]
        print(json.dumps({k: r[k] for k in ("answer", "citations", "abstained", "session_id")},
                         indent=2, ensure_ascii=False))
        print(f"  ({r['meta']['latency_ms']['total_ms']} ms, cache_hit={r['meta']['cache_hit']})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("ingest", help="load the KB into Pinecone")
    p.add_argument("--dry-run", action="store_true", help="only show what would be ingested")
    p = sub.add_parser("ask", help="answer one question as JSON")
    p.add_argument("question", nargs="+")
    sub.add_parser("chat", help="interactive chat in one session")
    p = sub.add_parser("eval", help="scored test run, writes reports/")
    p.add_argument("--models", nargs="+", default=[CHAT_MODEL], help="compare chat models")
    p = sub.add_parser("serve", help="start the web UI + JSON API")
    p.add_argument("--port", type=int, default=8000)
    sub.add_parser("test", help="offline tests, no API calls")
    args = parser.parse_args()

    if args.command == "ingest":
        from vectra.ingest import ingest
        ingest(args.dry_run)
    elif args.command == "ask":
        from vectra import answer
        print(json.dumps(answer(" ".join(args.question)), indent=2, ensure_ascii=False))
    elif args.command == "chat":
        chat()
    elif args.command == "eval":
        from vectra.evaluation import run_eval
        return run_eval(args.models)
    elif args.command == "serve":
        import uvicorn
        from vectra.api import app
        uvicorn.run(app, host="127.0.0.1", port=args.port)
    elif args.command == "test":
        import pytest
        return pytest.main([str(Path(__file__).parent / "tests"), "-q", "-p", "no:cacheprovider"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
