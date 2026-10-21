"""Nickname + password accounts, adapted from HW4's Campus Customs login.

Security choices:
- No email or real name is collected. A nickname and a password are enough to play.
- Passwords are never stored. Only a salted PBKDF2-SHA256 hash (600,000 rounds) is kept:
  "pbkdf2_sha256$600000$<salt>$<hex digest>".
- Login sessions are random 256-bit tokens kept in an HttpOnly cookie. The database only
  holds a SHA-256 hash of each token, so a leaked database can't be used to log in as anyone.
- A wrong nickname takes as long as a wrong password, so nobody can probe which nicknames exist.
- Repeated failed logins are slowed down per nickname and per IP address.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone

import db

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 600_000
SESSION_DAYS = 14
MAX_FAILED_PER_NICK = 5
MAX_FAILED_PER_IP = 20
LOCKOUT_SECONDS = 15 * 60
MIN_PASSWORD = 8
MAX_PASSWORD = 128
NICK_RE = re.compile(r"^[A-Za-z0-9 ._'-]{2,24}$")
AVATARS = {"joey", "liberty", "vedant", "taft", "clinton", "bushw", "desantis", "washington", "lincoln", "troosevelt", "fdr", "truman", "eisenhower", "jfk",
           "reagan", "obama", "trump", "biden", "vance", "harris"}


class AuthError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


# ---------- passwords ----------

def _pbkdf2(password: str, salt: str, iterations: int) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations).hex()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    return f"{ALGORITHM}${ITERATIONS}${salt}${_pbkdf2(password, salt, ITERATIONS)}"


def verify_password(password: str, stored: str) -> bool:
    parts = stored.split("$")
    if len(parts) != 4 or parts[0] != ALGORITHM or not parts[1].isdigit():
        return False
    return hmac.compare_digest(_pbkdf2(password, parts[2], int(parts[1])), parts[3])


_DUMMY_HASH = hash_password(secrets.token_hex(16))


# ---------- accounts ----------

def clean_nickname(nick: str) -> str:
    nick = re.sub(r"\s+", " ", (nick or "").strip())
    if not NICK_RE.match(nick):
        raise AuthError(400, "Nicknames are 2 to 24 letters, numbers, spaces, or . _ ' -")
    return nick


def public_user(row: sqlite3.Row) -> dict:
    """The only account fields ever sent to the browser. Never the password hash."""
    return {"id": row["id"], "nickname": row["nickname"], "avatar": row["avatar"]}


def create_user(nickname: str, password: str, avatar: str) -> dict:
    nick = clean_nickname(nickname)
    if not (MIN_PASSWORD <= len(password or "") <= MAX_PASSWORD):
        raise AuthError(400, f"Passwords need {MIN_PASSWORD} to {MAX_PASSWORD} characters.")
    if avatar not in AVATARS:
        raise AuthError(400, "Pick one of the Labubu avatars.")
    with db.connect() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO users (nickname, nickname_key, avatar, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                (nick, nick.lower(), avatar, hash_password(password), db.now()))
        except sqlite3.IntegrityError:
            raise AuthError(409, "That nickname is taken. Try another one.")
        row = conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
    return public_user(row)


def authenticate(nickname: str, password: str) -> dict | None:
    key = re.sub(r"\s+", " ", (nickname or "").strip()).lower()
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE nickname_key = ?", (key,)).fetchone()
    if row is None:
        verify_password(password or "", _DUMMY_HASH)  # same work as a real check
        return None
    return public_user(row) if verify_password(password or "", row["password_hash"]) else None


def set_avatar(user_id: int, avatar: str) -> None:
    if avatar not in AVATARS:
        raise AuthError(400, "Pick one of the Labubu avatars.")
    with db.connect() as conn:
        conn.execute("UPDATE users SET avatar = ? WHERE id = ?", (avatar, user_id))


# ---------- sessions ----------

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    with db.connect() as conn:
        conn.execute("INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                     (_token_hash(token), user_id, db.now(), expires.isoformat(timespec="seconds")))
    return token


def user_for_session(token: str | None) -> dict | None:
    if not token:
        return None
    with db.connect() as conn:
        row = conn.execute(
            "SELECT users.* FROM sessions JOIN users ON users.id = sessions.user_id"
            " WHERE sessions.token_hash = ? AND sessions.expires_at > ?", (_token_hash(token), db.now())).fetchone()
    return public_user(row) if row else None


def delete_session(token: str | None) -> None:
    if token:
        with db.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))


# ---------- login rate limiting ----------

_failures: dict[str, list[float]] = {}
_lock = threading.Lock()


def _recent(key: str, t: float) -> list[float]:
    stamps = [s for s in _failures.get(key, []) if t - s < LOCKOUT_SECONDS]
    _failures[key] = stamps
    return stamps


def login_blocked(nick_key: str, ip: str) -> bool:
    t = time.monotonic()
    with _lock:
        return len(_recent("n:" + nick_key, t)) >= MAX_FAILED_PER_NICK or len(_recent("ip:" + ip, t)) >= MAX_FAILED_PER_IP


def record_failure(nick_key: str, ip: str) -> None:
    t = time.monotonic()
    with _lock:
        _recent("n:" + nick_key, t).append(t)
        _recent("ip:" + ip, t).append(t)


def clear_failures(nick_key: str) -> None:
    with _lock:
        _failures.pop("n:" + nick_key, None)
