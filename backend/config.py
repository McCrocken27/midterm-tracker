"""Settings for the backend: where the .env file is, which model to use, and the safety limits.

The .env file is looked for in two places, in this order (as the project rules require):
  1. the repo's own folder (the folder that contains backend/ and docs/)
  2. the folder above it
The first file found wins for any key it sets.
"""

from __future__ import annotations

import os
from pathlib import Path

import truststore
from dotenv import load_dotenv

truststore.inject_into_ssl()  # use the operating system's certificate store for HTTPS

BACKEND_DIR = Path(__file__).resolve().parent
REPO_DIR = BACKEND_DIR.parent
SITE_DIR = REPO_DIR / "docs"
DATA_DIR = BACKEND_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

ENV_PATHS = [REPO_DIR / ".env", REPO_DIR.parent / ".env"]
for _p in ENV_PATHS:
    load_dotenv(_p, override=False)
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")


def env_file_used() -> str | None:
    """Which .env file supplied the key (for the health check). Never returns the key itself."""
    for p in ENV_PATHS:
        if p.exists() and "PORTKEY_API_KEY" in p.read_text(encoding="utf-8", errors="ignore"):
            return "repo folder" if p.parent == REPO_DIR else "one folder up"
    return None


PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
# The course key only allows the course model. Override with MODEL_NAME in .env if needed.
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-6-luna")
MODEL_TIMEOUT_SECONDS = 60

DB_PATH = Path(os.getenv("DB_PATH", str(DATA_DIR / "tracker.db")))

# ---- safety and cost limits ----
MAX_QUESTION_CHARS = 500          # longest question the agents will read
MAX_TOOL_CALLS_PER_RUN = 10       # loop cap: tool calls per agent run
MAX_AGENT_REQUESTS = 10           # loop cap: model requests per agent run
MAX_OUTPUT_TOKENS = 800           # per model response
DAILY_TOKEN_BUDGET = int(os.getenv("DAILY_TOKEN_BUDGET", "200000"))  # all agents, all users, per day
ASK_PER_USER_PER_HOUR = 10        # questions per logged-in user per hour
ASK_PER_IP_PER_HOUR = 30          # questions per IP address per hour

# Picks lock at 6 AM Eastern on Election Day (Nov 3, 2026 is after daylight saving ends: UTC-5).
PICKS_CLOSE_UTC = "2026-11-03T11:00:00+00:00"
POINTS_PER_CORRECT = 10
