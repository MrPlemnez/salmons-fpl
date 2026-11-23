#!/usr/bin/env python3
"""Sanity-check site/data.json before it is deployed. Exits non-zero if anything essential is
missing or obviously wrong, so the workflow keeps the last good site instead of publishing junk.

    python3 scripts/check_data.py
"""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
problems = []


def need(cond, msg):
    if not cond:
        problems.append(msg)


try:
    d = json.loads((ROOT / "site" / "data.json").read_text())
except Exception as e:  # noqa: BLE001
    print(f"data.json unreadable: {e}")
    sys.exit(1)

cfg = json.loads((ROOT / "config.json").read_text())
m = d.get("meta", {})
managers = d.get("managers", [])
need(len(managers) == len(cfg["managers"]), f"{len(managers)} managers, expected {len(cfg['managers'])}")
need(m.get("updated"), "no updated time")
if m.get("updated"):
    age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(m["updated"])
    need(age < dt.timedelta(minutes=30), f"data is {age} old")
after = m.get("after") or 0
if after:
    st = d.get("standings", [])
    need(len(st) == len(managers), f"standings has {len(st)} rows")
    need(all(isinstance(s.get("total"), int) and s["total"] > 0 for s in st), "standings totals missing or zero")
    ids = {x["id"] for x in managers}
    need({s["id"] for s in st} == ids, "standings managers don't match the league")
    for eid, row in (d.get("scores") or {}).items():
        need(len(row) == after and all(v is not None for v in row), f"scores for {eid} incomplete")
    need(str(after) in (d.get("gws") or {}), f"no Team of the Week data for GW{after}")
need(len(d.get("players", {})) > 300, f"only {len(d.get('players', {}))} players")
if m.get("current") and not m.get("final"):
    need(d.get("live") and len(d["live"].get("managers", [])) == len(managers), "live view missing")
for i in m.get("issues", []):
    print(f"warning: {i}")

if problems:
    print("data.json failed checks:")
    for p in problems:
        print(f"  - {p}")
    sys.exit(1)
print(f"data.json OK: after GW{after}, current GW{m.get('current')}, {len(d['players'])} players")
