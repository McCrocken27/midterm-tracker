"""Code-based defenses around the agents. None of these use the model, so they can't be talked out of their rules.

1. screen_question: blocks prompt-injection and data-theft attempts before any agent sees them.
2. clean_untrusted: strips and fences text from web pages before the Results agent reads it.
3. filter_output: blocks any answer that looks like it contains a password hash, key, token or email.
4. RateLimiter + budget_left: stop a bug or a bad actor from burning through the token budget.
"""

from __future__ import annotations

import html
import re
import threading
import time
from datetime import datetime, timezone

import db
from config import DAILY_TOKEN_BUDGET, MAX_QUESTION_CHARS

# Phrases that try to override the agents' instructions or pull private data out of the app.
INJECTION = [
    r"\bignore\b.{0,30}\b(instructions?|rules?|prompts?|above|previous|prior)\b",
    r"\b(disregard|forget|override|bypass)\b.{0,30}\b(instructions?|rules?|guardrails?|system|safety)\b",
    r"\b(system|developer|hidden)\s*(prompt|message|instructions?)\b",
    r"\byou\s+are\s+now\b|\bact\s+as\b|\bpretend\s+(to\s+be|you)\b|\bjailbreak\b|\bDAN\b|\bdeveloper\s+mode\b",
    r"\b(show|print|reveal|list|dump|give|tell|leak|export|send)\b.{0,40}\b(passwords?|password\s*hash(es)?|hash(es)?|tokens?|sessions?|cookies?|api\s*keys?|secrets?|\.env|credentials?|portkey)\b",
    r"\b(users?|accounts?|sessions?|nicknames?)\s+(table|database|db|list)\b",
    r"\b(select|insert|update|delete|drop|alter)\b\s+.{0,40}\b(from|into|table|users|sessions)\b",
    r"<\s*/?\s*(script|iframe|img|svg)\b|javascript:",
    r"\bother\s+(players?|users?)'?\s*(picks|passwords|accounts)\b",
]
INJECTION_RE = [re.compile(p, re.I) for p in INJECTION]

# Things that must never leave the server in an answer.
SECRET_PATTERNS = [
    (re.compile(r"pbkdf2_sha256\$"), "password hash"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{10,}"), "API key"),
    (re.compile(r"PORTKEY_API_KEY|password_hash|token_hash", re.I), "internal field name"),
    (re.compile(r"\b[0-9a-f]{40,}\b", re.I), "long hex token"),
    (re.compile(r"\b[A-Za-z0-9_-]{43,}\b"), "long session-style token"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "email address"),
]


# Names other players can see (league names) must be kid-friendly. Checked after removing spaces,
# dots and number-for-letter swaps, so "b a d" or "b4d" style tricks are caught too.
NOT_KID_FRIENDLY = ("fuck", "shit", "bitch", "cunt", "dick", "cock", "pussy", "asshole", "bastard", "slut", "whore",
                    "nigg", "fag", "retard", "porn", "sex", "nazi", "hitler", "kkk", "rape", "penis", "vagina", "boob",
                    "tits", "damn", "crap", "piss", "hell", "kill", "die", "hate", "stupid", "idiot", "dumb", "loser")


def kid_friendly(text: str) -> bool:
    t = (text or "").lower().translate(str.maketrans("013457@$!", "oieastasi"))
    squashed = re.sub(r"[^a-z]", "", t)
    words = set(re.findall(r"[a-z]+", t))
    # whole words only, so "Grapefruit", "Hancock" or "Hello" are fine
    short = {"hell", "die", "kill", "hate", "dumb", "crap", "damn", "sex", "kkk", "fag", "piss", "rape", "dick", "cock", "tits", "boob", "penis"}
    return not any((w in words) if w in short else (w in squashed) for w in NOT_KID_FRIENDLY)


def screen_question(q: str) -> tuple[bool, str]:
    """True if the question may go to the agents. Logs every block."""
    q = (q or "").strip()
    if not q:
        return False, "Ask a question about a race."
    if len(q) > MAX_QUESTION_CHARS:
        db.log_safety("too_long", f"{len(q)} chars")
        return False, f"Keep questions under {MAX_QUESTION_CHARS} characters."
    for rx in INJECTION_RE:
        if rx.search(q):
            db.log_safety("prompt_injection", q[:200])
            return False, "I can only answer questions about the races. I can't change my rules or share private data."
    return True, ""


def clean_untrusted(text: str, limit: int = 6000) -> tuple[str, bool]:
    """Strip HTML from a web page and fence it as data. Returns (text, looked_like_an_attack)."""
    text = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", text or "")
    text = re.sub(r"(?s)<!--.*?-->", " ", text)          # hidden comments are a classic hiding place
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"\s+", " ", text).strip()[:limit]
    attack = any(rx.search(text) for rx in INJECTION_RE)
    if attack:
        db.log_safety("injection_in_page", text[:200])
    return text, attack


def filter_output(text: str) -> tuple[bool, str]:
    for rx, what in SECRET_PATTERNS:
        if rx.search(text or ""):
            db.log_safety("output_blocked", what)
            return False, what
    return True, ""


class RateLimiter:
    """Sliding-window counter: at most `limit` events per `window` seconds per key."""

    def __init__(self, limit: int, window: float = 3600):
        self.limit, self.window = limit, window
        self.events: dict[str, list[float]] = {}
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        t = time.monotonic()
        with self.lock:
            stamps = [s for s in self.events.get(key, []) if t - s < self.window]
            if len(stamps) >= self.limit:
                self.events[key] = stamps
                return False
            stamps.append(t)
            self.events[key] = stamps
            return True


def tokens_used_today() -> int:
    day = datetime.now(timezone.utc).date().isoformat()
    with db.connect() as conn:
        row = conn.execute("SELECT COALESCE(SUM(input_tokens + output_tokens), 0) AS n FROM token_usage WHERE day = ?",
                           (day,)).fetchone()
    return int(row["n"])


def budget_left() -> int:
    return DAILY_TOKEN_BUDGET - tokens_used_today()
