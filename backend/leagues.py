"""Private leagues: a group of friends with their own leaderboard, joined with a code like "K7TQ2MXB".

Rules (all enforced here, never trusted from the browser):
- You need an account to make or join a league.
- Codes are 8 random characters with no vowels, so a code can never spell a word, and there are
  about 377 billion of them, so nobody can guess one. Join attempts are also rate limited (see main.py).
- League names must be kid-friendly (safety.kid_friendly) and use plain characters.
- Only members can see a league's code, members or leaderboard.
- Limits: 5 leagues made per person, 10 joined per person, 50 members per league.
- The league leaderboard is the same as the main one (avatar, nickname, points, badges), just for members.
"""

from __future__ import annotations

import re
import secrets
import sqlite3

import db
import game
import safety

ALPHABET = "BCDFGHJKLMNPQRSTVWXZ23456789"   # no vowels, no 0/O or 1/I mix-ups
CODE_LEN, MAX_OWNED, MAX_JOINED, MAX_MEMBERS = 8, 5, 10, 50
NAME_RE = re.compile(r"^[A-Za-z0-9 ._'!&-]{3,30}$")


class LeagueError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def _clean_name(name: str) -> str:
    name = re.sub(r"\s+", " ", (name or "").strip())
    if not NAME_RE.match(name):
        raise LeagueError(400, "League names are 3 to 30 letters, numbers, spaces, or . _ ' ! & -")
    if not safety.kid_friendly(name):
        raise LeagueError(400, "Please pick a kid-friendly league name.")
    return name


def _clean_code(code: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (code or "").upper())[:CODE_LEN]


def _summary(conn: sqlite3.Connection, row: sqlite3.Row, user_id: int) -> dict:
    n = conn.execute("SELECT COUNT(*) FROM league_members WHERE league_id = ?", (row["id"],)).fetchone()[0]
    return {"id": row["id"], "name": row["name"], "code": row["code"], "members": n, "owner": row["owner_id"] == user_id}


def my_leagues(user_id: int) -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute("SELECT leagues.* FROM leagues JOIN league_members m ON m.league_id = leagues.id"
                            " WHERE m.user_id = ? ORDER BY leagues.name", (user_id,)).fetchall()
        return [_summary(conn, r, user_id) for r in rows]


def create(user_id: int, name: str) -> dict:
    name = _clean_name(name)
    with db.connect() as conn:
        if conn.execute("SELECT COUNT(*) FROM leagues WHERE owner_id = ?", (user_id,)).fetchone()[0] >= MAX_OWNED:
            raise LeagueError(400, f"You can make up to {MAX_OWNED} leagues.")
        if conn.execute("SELECT COUNT(*) FROM league_members WHERE user_id = ?", (user_id,)).fetchone()[0] >= MAX_JOINED:
            raise LeagueError(400, f"You can be in up to {MAX_JOINED} leagues.")
        for _ in range(5):
            code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LEN))
            try:
                cur = conn.execute("INSERT INTO leagues (name, code, owner_id, created_at) VALUES (?, ?, ?, ?)",
                                   (name, code, user_id, db.now()))
                break
            except sqlite3.IntegrityError:
                continue
        else:
            raise LeagueError(503, "Couldn't make a code. Try again.")
        conn.execute("INSERT INTO league_members (league_id, user_id, joined_at) VALUES (?, ?, ?)", (cur.lastrowid, user_id, db.now()))
        return _summary(conn, conn.execute("SELECT * FROM leagues WHERE id = ?", (cur.lastrowid,)).fetchone(), user_id)


def join(user_id: int, code: str) -> dict:
    code = _clean_code(code)
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM leagues WHERE code = ?", (code,)).fetchone() if len(code) == CODE_LEN else None
        if row is None:
            raise LeagueError(404, "No league has that code. Check it with your friend.")
        if conn.execute("SELECT 1 FROM league_members WHERE league_id = ? AND user_id = ?", (row["id"], user_id)).fetchone():
            return _summary(conn, row, user_id)
        if conn.execute("SELECT COUNT(*) FROM league_members WHERE user_id = ?", (user_id,)).fetchone()[0] >= MAX_JOINED:
            raise LeagueError(400, f"You can be in up to {MAX_JOINED} leagues.")
        if conn.execute("SELECT COUNT(*) FROM league_members WHERE league_id = ?", (row["id"],)).fetchone()[0] >= MAX_MEMBERS:
            raise LeagueError(400, "That league is full.")
        conn.execute("INSERT INTO league_members (league_id, user_id, joined_at) VALUES (?, ?, ?)", (row["id"], user_id, db.now()))
        return _summary(conn, row, user_id)


def _member_league(conn: sqlite3.Connection, user_id: int, league_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT leagues.* FROM leagues JOIN league_members m ON m.league_id = leagues.id"
                       " WHERE leagues.id = ? AND m.user_id = ?", (league_id, user_id)).fetchone()
    if row is None:   # same answer for "doesn't exist" and "not yours", so ids can't be probed
        raise LeagueError(404, "League not found.")
    return row


def leave(user_id: int, league_id: int) -> None:
    """Members leave. If the person who made the league leaves, the league is deleted."""
    with db.connect() as conn:
        row = _member_league(conn, user_id, league_id)
        if row["owner_id"] == user_id:
            conn.execute("DELETE FROM league_members WHERE league_id = ?", (league_id,))
            conn.execute("DELETE FROM leagues WHERE id = ?", (league_id,))
        else:
            conn.execute("DELETE FROM league_members WHERE league_id = ? AND user_id = ?", (league_id, user_id))


def leaderboard(user_id: int, league_id: int) -> dict:
    with db.connect() as conn:
        row = _member_league(conn, user_id, league_id)
        members = {r["user_id"] for r in conn.execute("SELECT user_id FROM league_members WHERE league_id = ?", (league_id,))}
        league = _summary(conn, row, user_id)
    return {**game.leaderboard(only=members), "league": league}
