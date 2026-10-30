# Hosting entry point. The code lives in code/vectra/; this only exposes its FastAPI app.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "code"))
from vectra.api import app  # noqa: E402,F401
