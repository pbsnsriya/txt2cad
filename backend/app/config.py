"""Runtime settings from the environment (and backend/.env). Paths are absolute so the app works from any working directory."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

DATA_DIR = Path(os.environ.get("TXT2CAD_DATA_DIR", BACKEND_DIR / "data"))
DB_PATH = Path(os.environ.get("TXT2CAD_DB_PATH", DATA_DIR / "txt2cad.sqlite3"))
HOST = os.environ.get("TXT2CAD_HOST", "127.0.0.1")
PORT = int(os.environ.get("TXT2CAD_PORT", 8770))
ALLOWED_ORIGINS = [o for o in os.environ.get("TXT2CAD_ORIGINS", "http://127.0.0.1:5174,http://localhost:5174").split(",") if o]
LOCAL_OWNER = "local"          # single-user while the server only listens on localhost
MAX_REPAIR_ROUNDS = int(os.environ.get("TXT2CAD_MAX_REPAIRS", 2))
MAX_STEPS_PER_ROUND = int(os.environ.get("TXT2CAD_MAX_STEPS", 140))        # a reply this long is not a design, it is a loop
MAX_REJECTED_PER_ROUND = int(os.environ.get("TXT2CAD_MAX_REJECTED", 25))
MAX_CALL_SECONDS = float(os.environ.get("TXT2CAD_MAX_CALL_SECONDS", 150))
MAX_RUN_SECONDS = float(os.environ.get("TXT2CAD_MAX_RUN_SECONDS", 330))
PREVIEW_KEEP = 6               # preview files kept per run
STREAM_PING_S = 1.0
