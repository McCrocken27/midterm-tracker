"""Midterm news for the site's News tab. Run it to refresh docs/news.json:

    python backend/news.py

Uses only Python's standard library, so the GitHub Action that refreshes the news every
few hours needs nothing installed. Sources are free public RSS feeds: Google News searches,
NPR Politics and PBS NewsHour Politics.

Filters, in order:
- Only stories from the last 14 days.
- Only stories about 2026 races: the words "midterm", a race phrase ("Senate race",
  "governor's race", "battleground"...), or a candidate or race name from the site's data
  together with an election word.
- Outlets behind a hard paywall are skipped, so every link can be read for free. Social media posts are skipped too.
- At most 8 stories per outlet, and at most 2 that share a headline template ("Texas Midterm
  Elections 2026: Key Races..." / "Ohio Midterm Elections 2026: Key Races...").
- Kid-friendly: stories with violent, sexual or drug words in the headline or summary are dropped.
- Only https links are kept. Headlines and short summaries are stored as plain text; the
  site shows them with textContent, never as HTML.
"""

from __future__ import annotations

import html
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "docs"
OUT = SITE / "news.json"
DAYS, MAX_ITEMS, MAX_FEED_BYTES = 14, 60, 2_000_000

GOOGLE = "https://news.google.com/rss/search?hl=en-US&gl=US&ceid=US:en&q="
FEEDS = [(GOOGLE + urllib.parse.quote(q + " when:7d"), "Google News") for q in (
    "2026 midterm elections", "2026 Senate race", "2026 governor race", "2026 House race", "midterms battleground district")]
FEEDS += [("https://feeds.npr.org/1014/rss.xml", "NPR"), ("https://www.pbs.org/newshour/feeds/rss/politics", "PBS News")]

PAYWALLED = ("wsj.com", "nytimes.com", "washingtonpost.com", "bloomberg.com", "ft.com", "economist.com",
             "theatlantic.com", "newyorker.com", "barrons.com", "businessinsider.com", "latimes.com",
             "bostonglobe.com", "politicopro.com", "thetimes.co.uk", "telegraph.co.uk")
NOT_NEWS = ("facebook.com", "instagram.com", "x.com", "twitter.com", "youtube.com", "tiktok.com", "reddit.com", "threads.net")
PER_OUTLET, PER_TEMPLATE = 8, 2   # so one outlet's 50 state guides can't fill the whole page
MIDTERM = re.compile(r"\bmidterms?\b|\b2026 (?:elections?|races?|ballot)\b|\bSenate (?:race|seat|contest|primary)\b|"
                     r"\bHouse (?:race|seat|majority|control)\b|\bgovernor'?s race\b|\bgubernatorial\b|\bbattleground\b|"
                     r"\bswing (?:district|state|seat)s?\b|\bcontrol of (?:the )?(?:House|Senate|Congress)\b|\bcongressional (?:race|district|seat)s?\b", re.I)
ELECTION = re.compile(r"\belect|\brace\b|\bcampaign|\bcandidate|\bpolls?\b|\bpolling\b|\bvot(?:e|er|ers|ing)\b|\bballot|\bdebate|"
                      r"\bnominee|\bendorse|\bfundrais|\bad\b|\bads\b|\bconcede|\bwins?\b|\bleads?\b", re.I)
NOT_FOR_KIDS = re.compile(r"\b(?:shoot\w*|shot dead|gun\w*|kill\w*|murder\w*|stab\w*|rape\w*|sex\w*|porn\w*|nude|naked|"
                          r"suicide|overdose|drugs?|cocaine|fentanyl|assault\w*|abus\w*|molest\w*|bomb\w*|terror\w*|"
                          r"behead\w*|massacre|slur\w*|f\*+|s\*+t)\b", re.I)


def _grab(src: str, name: str, closer: str) -> str:
    start = src.index("var " + name + "=") + len(name) + 5
    return src[start:src.index(closer, start) + len(closer) - 1]


def _state_names() -> list[str]:
    src = (SITE / "index.html").read_text(encoding="utf-8")
    return re.findall(r'[A-Z]{2}:"([^"]+)"', _grab(src, "NAMES", "};"))


def race_index() -> list[tuple[re.Pattern, str]]:
    """(pattern, race id) pairs: candidates' full names, plus "Texas Senate" / "Ohio governor" style names."""
    src = (SITE / "index.html").read_text(encoding="utf-8")
    data = json.loads(_grab(src, "DATA", "]]];"))
    ind = json.loads(re.sub(r",\s*}", "}", _grab(src, "IND", "};")))
    names = dict(re.findall(r'([A-Z]{2}):"([^"]+)"', _grab(src, "NAMES", "};")))
    out = []
    for x in data:
        rid, ch, st = x[0], x[1], x[2]
        for n in {x[8], x[9], ind.get(rid, "")}:
            if n and n != "-" and " " in n:
                out.append((re.compile(r"\b" + re.escape(n) + r"\b"), rid))
        if ch in "sg" and st in names:
            word = r"Senate" if ch == "s" else r"(?:governor|gubernatorial)"
            guard = r"(?<!West )" if names[st] == "Virginia" else ""
            out.append((re.compile(guard + r"\b" + re.escape(names[st]) + r"(?:['’]s)? (?:U\.?S\.? )?" + word + r"\b", re.I), rid))
        if ch == "h" and st in names:
            d = int(x[3] or 0)
            nth = "at-large" if not d else str(d) + ("th" if 10 <= d % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(d % 10, "th"))
            out.append((re.compile(r"\b" + re.escape(names[st]) + r"['’]s " + nth + r" (?:Congressional )?District\b", re.I), rid))
            out.append((re.compile(r"\b" + st + r"-0?" + (str(d) if d else "AL") + r"\b"), rid))   # "IA-01", "IA-1"
    return out


def _text(s: str | None) -> str:
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "midterm-tracker-news/1.0 (school project)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read(MAX_FEED_BYTES)


def parse(xml: bytes, feed_name: str) -> list[dict]:
    items = []
    for it in ET.fromstring(xml).iter("item"):
        title, link = _text(it.findtext("title")), (it.findtext("link") or "").strip()
        src_el = it.find("source")
        outlet, outlet_url = (_text(src_el.text), src_el.get("url", "")) if src_el is not None else (feed_name, link)
        if src_el is not None and title.endswith(" - " + outlet):
            title = title[: -len(outlet) - 3]
        summary = "" if feed_name == "Google News" else _text(it.findtext("description"))
        try:
            when = parsedate_to_datetime(it.findtext("pubDate") or "").astimezone(timezone.utc)
        except (TypeError, ValueError):
            continue
        items.append({"t": title, "src": outlet, "src_url": outlet_url, "url": link, "when": when, "sum": summary})
    return items


def keep(item: dict, index, cutoff: datetime) -> list[str] | None:
    """The race ids a story is about ([] = midterms in general), or None to drop it."""
    text = item["t"] + " " + item["sum"]
    if item["when"] < cutoff or not item["url"].startswith("https://") or not item["t"]:
        return None
    host = urllib.parse.urlparse(item["src_url"]).netloc.lower()
    if any(host == d or host.endswith("." + d) for d in PAYWALLED + NOT_NEWS) or NOT_FOR_KIDS.search(text):
        return None
    races = sorted({rid for pat, rid in index if pat.search(text)})
    if MIDTERM.search(text) or (races and ELECTION.search(text)):
        return races
    return None


def build(fetch=_fetch, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    index, cutoff, seen, out, used = race_index(), now - timedelta(days=DAYS), set(), [], []
    states = re.compile(r"\b(?:" + "|".join(sorted(map(re.escape, _state_names()), key=len, reverse=True)) + r")\b")
    per_outlet: dict[str, int] = {}
    per_template: dict[str, int] = {}
    for url, name in FEEDS:
        try:
            items = parse(fetch(url), name)
        except Exception as e:  # one broken feed shouldn't stop the others
            print(f"skipped {name}: {type(e).__name__}", file=sys.stderr)
            continue
        if name not in used:
            used.append(name)
        for item in items:
            key = re.sub(r"[^a-z0-9]+", " ", item["t"].lower()).strip()
            races = keep(item, index, cutoff)
            template = states.sub("#", item["t"]).lower()
            if races is None or key in seen or per_outlet.get(item["src"], 0) >= PER_OUTLET or per_template.get(template, 0) >= PER_TEMPLATE:
                continue
            seen.add(key)
            per_outlet[item["src"]] = per_outlet.get(item["src"], 0) + 1
            per_template[template] = per_template.get(template, 0) + 1
            out.append({"t": item["t"][:200], "src": item["src"][:60], "url": item["url"], "d": item["when"].isoformat(timespec="minutes"),
                        "sum": (item["sum"][:220].rsplit(" ", 1)[0] + "...") if len(item["sum"]) > 220 else item["sum"], "races": races})
    out.sort(key=lambda x: x["d"], reverse=True)
    return {"updated": now.isoformat(timespec="minutes"), "sources": used, "items": out[:MAX_ITEMS]}


if __name__ == "__main__":
    news = build()
    if not news["items"] and OUT.exists():
        sys.exit("No stories found (feeds down?). Keeping the old news.json.")
    OUT.write_text(json.dumps(news, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"Wrote {len(news['items'])} stories from {', '.join(news['sources'])} to {OUT}")
