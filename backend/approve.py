"""Human approval for election results. Nothing reaches the leaderboard without a "y" here.

Usage (from the backend folder):
    .venv/Scripts/python approve.py                  # review the Results agent's suggestions one by one
    .venv/Scripts/python approve.py set sen-tx R     # enter a result by hand (you confirm it first)
"""

from __future__ import annotations

import sys

import db
import game
import races


def review() -> None:
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM proposals WHERE status = 'pending' ORDER BY id").fetchall()
    if not rows:
        print("No suggestions waiting.")
        return
    for p in rows:
        r = races.races().get(p["race_id"], {})
        who = next((c["name"] for c in r.get("candidates", []) if c["key"] == p["winner"]), p["winner"])
        print(f"\n{r.get('name', p['race_id'])}: winner {who}\n  evidence: {p['evidence']}\n  source:   {p['source']}")
        ans = input("Approve? [y = yes, n = reject, anything else = skip] ").strip().lower()
        if ans == "y":
            game.approve_result(p["race_id"], p["winner"], p["source"])
            status = "approved"
        elif ans == "n":
            status = "rejected"
        else:
            continue
        with db.connect() as conn:
            conn.execute("UPDATE proposals SET status = ? WHERE id = ?", (status, p["id"]))
        print("  ->", status)


def set_by_hand(race_id: str, key: str) -> None:
    r = races.races().get(race_id)
    if not r or key not in races.valid_pick_keys(race_id):
        print("Unknown race or candidate. Keys:", sorted(races.valid_pick_keys(race_id)))
        return
    who = next(c["name"] for c in r["candidates"] if c["key"] == key)
    if input(f"Record {who} as the winner of {r['name']}? [y/n] ").strip().lower() == "y":
        game.approve_result(race_id, key, "entered by hand")
        print("Saved.")


if __name__ == "__main__":
    db.init()
    if len(sys.argv) == 4 and sys.argv[1] == "set":
        set_by_hand(sys.argv[2].lower(), sys.argv[3])
    else:
        review()
