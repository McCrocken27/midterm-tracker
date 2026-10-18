"""Build report.html and slides.html with every screenshot embedded, so they open by double-clicking anywhere.

Usage (from the repo folder):  python report/build.py
Reads report/*_src.html, replaces {{IMG:name|caption}} with an embedded <figure>, and {{SRC:name}} with a data URI.
"""

import base64
import html as htmllib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "evidence" / "shots"


def data_uri(name: str) -> str:
    return "data:image/jpeg;base64," + base64.b64encode((SHOTS / f"{name}.jpg").read_bytes()).decode()


def figure(m: re.Match) -> str:
    name, caption = m.group(1), m.group(2)
    return f'<figure><img src="{data_uri(name)}" alt="{htmllib.escape(caption, quote=True)}"><figcaption>{caption}</figcaption></figure>'


for src, out in [("report_src.html", "report.html"), ("slides_src.html", "slides.html")]:
    p = ROOT / "report" / src
    if not p.exists():
        continue
    html = p.read_text(encoding="utf-8")
    html = re.sub(r"\{\{IMG:([\w-]+)\|([^}]*)\}\}", figure, html)
    html = re.sub(r"\{\{SRC:([\w-]+)\}\}", lambda m: data_uri(m.group(1)), html)
    (ROOT / out).write_text(html, encoding="utf-8")
    print(f"wrote {out} ({len(html) // 1024} KB)")
