"""Settings, read once from local/.env (or the host's environment variables)."""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent          # code/
LOCAL_DIR = ROOT.parent / "local"                       # keys, logs, backups - never committed or deployed
# override=True: this project's .env wins over leftover variables in the shell (this machine has an
# old REDIS_URL set globally). Hosted deployments have no .env, so their env vars apply as usual.
load_dotenv(LOCAL_DIR / ".env", override=True)

# --- OpenAI + Pinecone
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")
EMBED_DIM = int(os.getenv("EMBED_DIM", "1536"))
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4.1-mini")   # beat gpt-4o-mini in eval, similar speed

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX = os.getenv("PINECONE_INDEX", "vectra-kb")
PINECONE_CLOUD = os.getenv("PINECONE_CLOUD", "aws")
PINECONE_REGION = os.getenv("PINECONE_REGION", "us-east-1")

# --- Files
KB_DIR = Path(os.getenv("KB_DIR", ROOT.parent / "docs" / "kb"))   # the KB-*.md articles
MANIFEST_PATH = ROOT / "kb_manifest.json"           # written by ingest, read at startup
LOG_PATH = LOCAL_DIR / "logs" / "requests.jsonl"
REPORT_DIR = ROOT / "reports"
UI_PATH = ROOT / "web" / "index.html"

# --- Retrieval
TOP_K = int(os.getenv("TOP_K", "3"))
# Below this cosine score an article is treated as "not about this question".
# Eval scores: correct article 0.44-0.65, best match for questions the KB doesn't cover 0.19-0.31.
# 0.35 sits in that gap, but it rests on ~15 questions -> see DOCUMENTATION.md "What still fails".
MIN_SCORE = float(os.getenv("MIN_SCORE", "0.35"))

# --- Sessions
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "1800"))   # 30 min idle
SESSION_MAX_TURNS = int(os.getenv("SESSION_MAX_TURNS", "6"))
SESSION_HISTORY_FOR_LLM = 2                                           # turns sent to the model
MAX_SESSIONS = int(os.getenv("MAX_SESSIONS", "10000"))

# Sessions + answer cache live in memory by default. With more than one API instance (or serverless,
# serverless) instances don't share memory, so set ONE of these to keep them in Redis instead:
#   REDIS_URL=rediss://default:<password>@<host>:6379           any Redis (redis-py)
#   UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN            Upstash over HTTPS
#   KV_REST_API_URL + KV_REST_API_TOKEN                           same, alternative variable names
REDIS_URL = os.getenv("REDIS_URL", "")
REDIS_REST_URL = os.getenv("UPSTASH_REDIS_REST_URL") or os.getenv("KV_REST_API_URL", "")
REDIS_REST_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN") or os.getenv("KV_REST_API_TOKEN", "")

# --- Answer cache: most of the ~400 tickets/day are repeat questions
ANSWER_CACHE_TTL_SECONDS = int(os.getenv("ANSWER_CACHE_TTL_SECONDS", "3600"))
ANSWER_CACHE_SIZE = int(os.getenv("ANSWER_CACHE_SIZE", "2000"))

# --- LLM limits
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "20"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "400"))
MAX_QUESTION_CHARS = 2000

log = logging.getLogger("vectra")


def ms(start: float) -> float:
    """Milliseconds since a time.perf_counter() start."""
    return round((time.perf_counter() - start) * 1000, 1)
