"""Race data for the backend and the agents' tools.

The website (docs/index.html) is the single source of truth: this module reads the same
race list, ratings, model numbers, Joey's calls and the 37 prediction races straight out
of the page when the server starts, so the site and the backend can never disagree.

Everything here is read-only. Nothing in this module can see accounts, passwords or picks.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache

from config import SITE_DIR

OUTLETS = {
    "s": ["Cook Political Report", "Inside Elections", "Sabato's Crystal Ball", "The Economist", "Split Ticket",
          "Decision Desk HQ", "FiftyPlusOne", "Fox News", "Silver Bulletin", "RealClearPolitics"],
    "g": ["Cook Political Report", "Inside Elections", "Sabato's Crystal Ball", "Race to the WH", "RealClearPolitics",
          "Fox News", "Silver Bulletin", "Decision Desk HQ"],
}
OUTLETS["h"] = OUTLETS["s"]
LABEL = {"TU": "Toss-up", "TD": "Tilt D", "TR": "Tilt R", "LD": "Lean D", "LR": "Lean R", "YD": "Likely D",
         "YR": "Likely R", "SD": "Safe D", "SR": "Safe R"}
SCORE = {"TU": 0, "TD": .5, "TR": -.5, "LD": 1, "LR": -1, "YD": 2, "YR": -2, "SD": 3, "SR": -3}
CHAMBER = {"s": "senate", "g": "governor", "h": "house"}
PARTY = {"D": "Democratic", "R": "Republican", "I": "Independent"}


def _grab(src: str, name: str, closer: str) -> str:
    start = src.index("var " + name + "=") + len("var " + name + "=")
    end = src.index(closer, start) + len(closer) - (1 if closer.endswith(";") else 0)
    return src[start:end]


def _js_object(text: str):
    """The page's small JS object literals are JSON apart from trailing commas."""
    return json.loads(re.sub(r",\s*([}\]])", r"\1", text))


def consensus_label(score: float) -> str:
    a = abs(score)
    if a < .25:
        return "Toss-up"
    side = "D" if score > 0 else "R"
    return ("Safe" if a >= 2.5 else "Likely" if a >= 1.5 else "Lean" if a >= .75 else "Tilt") + " " + side


@lru_cache(maxsize=1)
def load() -> dict:
    src = (SITE_DIR / "index.html").read_text(encoding="utf-8")
    data = json.loads(_grab(src, "DATA", "]]];"))
    names = _js_object(re.sub(r"([{,]\s*)([A-Z]{2})\s*:", lambda m: m.group(1) + chr(34) + m.group(2) + chr(34) + ":", _grab(src, "NAMES", "};")))  # keys are unquoted state codes
    ind = _js_object(_grab(src, "IND", "};"))
    same = _js_object(_grab(src, "SAME", "};"))
    joey = _js_object(_grab(src, "JOEY", "};"))
    pred = _js_object(_grab(src, "PRED", "]]];"))
    defaults = _js_object(_grab(src, "DEF", "};"))
    races = {}
    for x in data:
        rid, ch, st, dist, lean, inc, party, status, dn, rn, note, codes, exc, mine, polls = x
        exc = dict((i, d) for i, d in exc)
        ratings = []
        for i, outlet in enumerate(OUTLETS[ch]):
            code = codes[2 * i:2 * i + 2]
            if code == "--":
                continue
            d = exc.get(i, defaults[ch][i])
            ratings.append({"outlet": outlet, "rating": LABEL[code], "as_of": f"2026-{d[:2]}-{d[2:]}", "_score": SCORE[code]})
        scores = [r.pop("_score") for r in ratings]
        mean = sum(scores) / len(scores) if scores else None
        # who is on the ballot, keyed the same way the site keys picks
        if rid in same:
            sp, second = same[rid]
            lineup = [[sp, rn if sp == "R" else dn], [sp + "2", second]]
        else:
            lineup = []
            if not (dn == "-" and rid in ind):
                lineup.append(["D", dn])
            if rid in ind:
                lineup.append(["I", ind[rid]])
            if not (rn == "-" and rid in ind):
                lineup.append(["R", rn])
        lean_txt = re.sub(r"^([RD])(\d+)$", r"\1+\2", lean)
        if ch == "h":
            name = f"{names.get(st, st)} {dist if dist else 'at-large'} ({st}-{'AL' if not dist else str(dist).zfill(2)})"
        else:
            name = f"{names.get(st, st)} {'Senate' if ch == 's' else 'governor'}"
        races[rid] = {
            "id": rid, "name": name, "chamber": CHAMBER[ch], "state": st, "district": dist, "lean": lean_txt,
            "incumbent": inc, "status": status, "note": note,
            "candidates": [{"key": k, "name": n, "party": PARTY[k[0]]} for k, n in lineup if n and n != "-"],
            "ratings": ratings,
            "consensus": None if mean is None else {"label": consensus_label(mean), "score": round(mean, 2), "outlets": len(scores)},
            "model": {"dem_pct": mine[0], "rep_pct": 100 - mine[0], "label": mine[1]},
            "joey": joey.get(rid, [None])[0],
            "polls": [{"pollster": p[0], "ended": p[1], "sample": p[2], "dem": p[3], "rep": p[4]} for p in polls],
        }
    pred_ids = [rid for _, ids in pred for rid in ids]
    return {"races": races, "names": names, "pred_ids": pred_ids}


def races() -> dict:
    return load()["races"]


def prediction_races() -> list[str]:
    return list(load()["pred_ids"])


def valid_pick_keys(race_id: str) -> set[str]:
    """The pick keys a player may choose for a race (one per candidate on the ballot)."""
    r = races().get(race_id)
    return {c["key"] for c in r["candidates"]} if r else set()


def state_code(text: str) -> str | None:
    """Turn 'Texas', 'tx' or 'TX' into 'TX'."""
    t = text.strip()
    names = load()["names"]
    if t.upper() in names:
        return t.upper()
    for code, full in names.items():
        if full.lower() == t.lower():
            return code
    return None
