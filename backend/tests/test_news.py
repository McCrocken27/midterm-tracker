"""News filters, tested offline with a made-up feed (no internet needed)."""

from datetime import datetime, timezone

import news

NOW = datetime(2026, 10, 21, 18, 0, tzinfo=timezone.utc)


def feed(*items):
    body = "".join(f"<item><title>{t}</title><link>{link}</link><pubDate>{d}</pubDate>"
                   f"<source url=\"{src}\">Outlet</source></item>" for t, link, d, src in items)
    return f"<rss><channel>{body}</channel></rss>".encode()


def run(*items):
    news.FEEDS[:] = [("https://example.test/feed", "Google News")]
    return news.build(fetch=lambda url: feed(*items), now=NOW)["items"]


RECENT, OLD, OK = "Wed, 21 Oct 2026 12:00:00 -0400", "Wed, 01 Oct 2026 12:00:00 -0400", "https://www.reuters.com"


def test_keeps_race_news_and_tags_the_race():
    items = run(("New poll in the Texas Senate race - Outlet", "https://news.example/a", RECENT, OK))
    assert [(i["t"], i["races"]) for i in items] == [("New poll in the Texas Senate race", ["sen-tx"])]


def test_drops_off_topic_old_paywalled_social_and_not_for_kids():
    items = run(("Supreme Court rules on a prison policy", "https://news.example/b", RECENT, OK),
                ("Midterm poll from three weeks ago", "https://news.example/c", OLD, OK),
                ("Midterm forecast update", "https://news.example/d", RECENT, "https://www.wsj.com"),
                ("Midterm rally video", "https://news.example/e", RECENT, "https://www.facebook.com"),
                ("Shooting near a midterm rally", "https://news.example/f", RECENT, OK),
                ("Midterm turnout record", "http://news.example/g", RECENT, OK))
    assert items == []


def test_caps_copycat_headlines():
    states = ["Texas", "Ohio", "Iowa", "Maine"]
    items = run(*[(f"{s} Midterm Elections 2026: Key Races", f"https://news.example/{s}", RECENT, OK) for s in states])
    assert len(items) == news.PER_TEMPLATE
