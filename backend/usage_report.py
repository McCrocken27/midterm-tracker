"""Tokenomics from real runs: tokens per question, per agent, cached share, and cost at given prices.

Usage (from the backend folder):
    .venv/Scripts/python usage_report.py
Optional prices (dollars per million tokens) in .env:  PRICE_INPUT_PER_M, PRICE_CACHED_PER_M, PRICE_OUTPUT_PER_M
"""

from __future__ import annotations

import os

import db

db.init()
with db.connect() as conn:
    runs = conn.execute("SELECT run_id, SUM(input_tokens) i, SUM(cached_tokens) c, SUM(output_tokens) o, SUM(requests) r"
                        " FROM token_usage WHERE agent != 'results' GROUP BY run_id").fetchall()
    by_agent = conn.execute("SELECT agent, COUNT(*) n, AVG(input_tokens) i, AVG(cached_tokens) c, AVG(output_tokens) o,"
                            " AVG(requests) r FROM token_usage GROUP BY agent ORDER BY agent").fetchall()
    blocked = conn.execute("SELECT kind, COUNT(*) n FROM safety_log GROUP BY kind ORDER BY n DESC").fetchall()

if not runs:
    print("No agent runs recorded yet. Ask Joey a few questions first.")
    raise SystemExit
n = len(runs)
avg_in = sum(r["i"] for r in runs) / n
avg_c = sum(r["c"] for r in runs) / n
avg_out = sum(r["o"] for r in runs) / n
print(f"Questions answered by the agents: {n}")
print(f"Average per question: {avg_in:.0f} input ({avg_c:.0f} cached), {avg_out:.0f} output, "
      f"{sum(r['r'] for r in runs) / n:.1f} model requests")
print("\nBy agent (average per call):")
for a in by_agent:
    print(f"  {a['agent']:<11} calls {a['n']:>3}   input {a['i']:>6.0f}   cached {a['c']:>5.0f}   output {a['o']:>5.0f}   requests {a['r']:.1f}")
pi, pc, po = (float(os.getenv(k, "0") or 0) for k in ("PRICE_INPUT_PER_M", "PRICE_CACHED_PER_M", "PRICE_OUTPUT_PER_M"))
if pi or po:
    per_q = ((avg_in - avg_c) * pi + avg_c * pc + avg_out * po) / 1e6
    print(f"\nCost per question: ${per_q:.5f}   per player (10 questions): ${per_q * 10:.4f}   "
          f"1,000 players: ${per_q * 10_000:.2f}")
print("\nSafety log:")
for b in blocked:
    print(f"  {b['kind']:<20} {b['n']}")
