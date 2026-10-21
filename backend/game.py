"""The prediction game: picks, the crowd view, approved results and the leaderboard.

Rules enforced here (never trusted from the browser):
- Only the 37 prediction races can be picked, and only with a key for a candidate on the ballot.
- Picks lock at 6 AM Eastern on Nov 3, 2026, by the server's clock.
- 10 points per race called correctly; points only show once results have been approved.
- The leaderboard shows nickname, avatar, points and badges. Nobody's individual picks are published.
- Badges say what kind of player you are (for example "picked against the forecasters at least once")
  without saying which races, so they don't give anyone's picks away.
"""

from __future__ import annotations

from datetime import datetime, timezone

import db
import races
from config import PICKS_CLOSE_UTC, POINTS_PER_CORRECT


class GameError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def picks_closed(at: datetime | None = None) -> bool:
    return (at or datetime.now(timezone.utc)) >= datetime.fromisoformat(PICKS_CLOSE_UTC)


def get_picks(user_id: int) -> dict[str, str]:
    with db.connect() as conn:
        rows = conn.execute("SELECT race_id, pick FROM picks WHERE user_id = ?", (user_id,)).fetchall()
    return {r["race_id"]: r["pick"] for r in rows}


def save_picks(user_id: int, picks: dict, at: datetime | None = None) -> dict[str, str]:
    """Replace this player's picks. Unknown races or keys are rejected, not silently dropped."""
    if picks_closed(at):
        raise GameError(403, "Picks are closed. Election Day has started.")
    if not isinstance(picks, dict) or len(picks) > len(races.prediction_races()):
        raise GameError(400, "Send a list of picks.")
    allowed = set(races.prediction_races())
    clean = {}
    for race_id, key in picks.items():
        if race_id not in allowed:
            raise GameError(400, f"{race_id} isn't one of the prediction races.")
        if key not in races.valid_pick_keys(race_id):
            raise GameError(400, f"That isn't a candidate in {race_id}.")
        clean[race_id] = key
    with db.connect() as conn:
        conn.execute("DELETE FROM picks WHERE user_id = ?", (user_id,))
        conn.executemany("INSERT INTO picks (user_id, race_id, pick, updated_at) VALUES (?, ?, ?, ?)",
                         [(user_id, r, k, db.now()) for r, k in clean.items()])
    return clean


def crowd() -> dict[str, dict[str, int]]:
    """How many players picked each candidate, per race (counts only, no names)."""
    with db.connect() as conn:
        rows = conn.execute("SELECT race_id, pick, COUNT(*) AS n FROM picks GROUP BY race_id, pick").fetchall()
    out: dict[str, dict[str, int]] = {}
    for r in rows:
        out.setdefault(r["race_id"], {})[r["pick"]] = r["n"]
    return out


def results() -> dict[str, str]:
    with db.connect() as conn:
        rows = conn.execute("SELECT race_id, winner FROM results").fetchall()
    return {r["race_id"]: r["winner"] for r in rows}


# Same rules as the BADGES list in docs/index.html. The last three only count once results are approved.
BADGES = ["all37", "bold", "tossup", "upset", "sharp", "beatjoey"]


def _favorite(race: dict) -> str | None:
    """The forecasters' favorite as a pick key ("D", "R" or "I"), "T" for a toss-up, None if unrated."""
    c = race.get("consensus")
    if not c:
        return None
    if abs(c["score"]) < .25:
        return "T"
    keys = [x["key"] for x in race["candidates"]]
    want = ["D", "I"] if c["score"] > 0 else ["R", "I"]
    return next((k for k in want if k in keys), None)


def badges(picks: dict[str, str], res: dict[str, str], joey_correct: int) -> list[str]:
    all_races, pred = races.races(), races.prediction_races()
    fav = {rid: _favorite(all_races[rid]) for rid in pred if rid in all_races}
    out = []
    if pred and all(rid in picks for rid in pred):
        out.append("all37")
    if any(fav.get(rid) not in (None, "T") and k != fav[rid] for rid, k in picks.items()):
        out.append("bold")
    tossups = [rid for rid, f in fav.items() if f == "T"]
    if tossups and all(rid in picks for rid in tossups):
        out.append("tossup")
    if res:
        decided = [rid for rid in picks if rid in res]
        correct = [rid for rid in decided if picks[rid] == res[rid]]
        if any(fav.get(rid) not in (None, "T") and fav[rid] != res[rid] for rid in correct):
            out.append("upset")
        if len(decided) >= 10 and len(correct) >= .8 * len(decided):
            out.append("sharp")
        if len(correct) > joey_correct:
            out.append("beatjoey")
    return out


def leaderboard(only: set[int] | None = None) -> dict:
    """Players with at least one pick (or, for a league, every member). Points appear only once results exist."""
    res = results()
    live = bool(res)
    with db.connect() as conn:
        users = conn.execute(
            "SELECT users.id, users.nickname, users.avatar FROM users"
            " WHERE EXISTS (SELECT 1 FROM picks WHERE picks.user_id = users.id) ORDER BY users.nickname_key").fetchall()
        if only is not None:
            users = conn.execute("SELECT users.id, users.nickname, users.avatar FROM users ORDER BY users.nickname_key").fetchall()
            users = [u for u in users if u["id"] in only]
        rows = conn.execute("SELECT user_id, race_id, pick FROM picks").fetchall()
    by_user: dict[int, dict[str, str]] = {}
    for r in rows:
        by_user.setdefault(r["user_id"], {})[r["race_id"]] = r["pick"]
    all_races = races.races()
    joey_correct = sum(1 for race_id, w in res.items() if all_races.get(race_id, {}).get("joey") == w)
    players = []
    for u in users:
        correct = sum(1 for race_id, w in res.items() if by_user.get(u["id"], {}).get(race_id) == w)
        players.append({"nickname": u["nickname"], "avatar": u["avatar"],
                        "points": correct * POINTS_PER_CORRECT if live else None,
                        "badges": badges(by_user.get(u["id"], {}), res, joey_correct)})
    if live:
        players.sort(key=lambda p: (-p["points"], p["nickname"].lower()))
    return {"live": live, "points_per_correct": POINTS_PER_CORRECT, "players": players, "results": res}


def approve_result(race_id: str, winner: str, source: str) -> None:
    """Called only from the approve.py command line, after a person says yes."""
    if race_id not in races.races() or winner not in races.valid_pick_keys(race_id):
        raise GameError(400, "Unknown race or candidate.")
    with db.connect() as conn:
        conn.execute("INSERT OR REPLACE INTO results (race_id, winner, source, approved_at) VALUES (?, ?, ?, ?)",
                     (race_id, winner, source[:300], db.now()))
