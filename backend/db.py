"""SQLite storage: accounts, sessions, picks, private leagues, approved results, result proposals,
token usage and the safety log.

Every query uses ? placeholders, so user input is never pasted into SQL.
The agents never import this module's account functions; see agents.py.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nickname TEXT NOT NULL,
    nickname_key TEXT NOT NULL UNIQUE,      -- lowercase, for "one account per nickname"
    avatar TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,            -- SHA-256 of the cookie token; the token itself is never stored
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS picks (
    user_id INTEGER NOT NULL REFERENCES users(id),
    race_id TEXT NOT NULL,
    pick TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, race_id)
);
CREATE TABLE IF NOT EXISTS results (       -- winners, only ever written after a human approves them
    race_id TEXT PRIMARY KEY,
    winner TEXT NOT NULL,
    source TEXT NOT NULL,
    approved_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS proposals (     -- the Results agent's suggestions, waiting for a human
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id TEXT NOT NULL,
    winner TEXT NOT NULL,
    source TEXT NOT NULL,
    evidence TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', -- pending / approved / rejected
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL,
    ts TEXT NOT NULL,
    run_id TEXT NOT NULL,
    agent TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    cached_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    requests INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS leagues (       -- private leagues; see leagues.py
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    code TEXT NOT NULL UNIQUE,
    owner_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS league_members (
    league_id INTEGER NOT NULL REFERENCES leagues(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    joined_at TEXT NOT NULL,
    PRIMARY KEY (league_id, user_id)
);
CREATE TABLE IF NOT EXISTS safety_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,
    detail TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now(),))


def log_safety(kind: str, detail: str) -> None:
    """Record a blocked attack or a tripped limit. Never stores passwords or tokens."""
    with connect() as conn:
        conn.execute("INSERT INTO safety_log (ts, kind, detail) VALUES (?, ?, ?)", (now(), kind, detail[:300]))
