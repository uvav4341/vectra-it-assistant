"""JSON-lines log of every request. Only masked text is ever written."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


def request_logger(path: Path) -> logging.Logger:
    logger = logging.getLogger(f"vectra.requests.{path}")
    if not logger.handlers:
        if os.getenv("VERCEL"):   # serverless host: read-only filesystem, stdout goes to its logs
            handler: logging.Handler = logging.StreamHandler(sys.stdout)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
