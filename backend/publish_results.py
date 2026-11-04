"""Publish approved election results to docs/results.json so the public site can show them.

Run this only after a person has approved every call in the file (each one needs a source).
Usage (from the backend folder):
    .venv/Scripts/python publish_results.py approved_calls.json

approved_calls.json is a list like:
    [{"race_id": "sen-ky", "winner": "R", "source": "https://apnews.com/..."}]
Unknown races, candidates not on the ballot, and calls without a source are rejected, not published.
New calls are merged into what is already published; a call that changes an earlier winner is printed so you can see it.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import races

OUT = Path(__file__).resolve().parents[1] / "docs" / "results.json"


def publish(calls: list[dict]) -> None:
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"results": {}}
    res = old.get("results", {})
    added = changed = 0
    for c in calls:
        rid, key, src = str(c.get("race_id", "")).lower(), str(c.get("winner", "")), str(c.get("source", "")).strip()
        r = races.races().get(rid)
        if not r or key not in races.valid_pick_keys(rid) or not src.startswith("https://"):
            print(f"REJECTED {rid} {key}: unknown race, candidate not on the ballot, or no https source")
            continue
        who = next(x["name"] for x in r["candidates"] if x["key"] == key)
        if rid in res and res[rid]["winner"] != key:
            print(f"CHANGED  {r['name']}: {res[rid]['winner']} -> {key} ({who})")
            changed += 1
        elif rid not in res:
            added += 1
        res[rid] = {"winner": key, "name": who, "source": src}
    eastern = datetime.now(timezone.utc) - timedelta(hours=5)  # Nov 3, 2026 is on standard time
    out = {"updated": eastern.strftime("%b %-d, %-I:%M %p ET") if sys.platform != "win32" else eastern.strftime("%b %#d, %#I:%M %p ET"),
           "results": dict(sorted(res.items()))}
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Published {len(res)} results ({added} new, {changed} changed) to {OUT.name}, updated {out['updated']}.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    publish(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
