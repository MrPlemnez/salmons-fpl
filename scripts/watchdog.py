#!/usr/bin/env python3
"""Is the published site fresh enough? Run by .github/workflows/watchdog.yml.

Prints "stale=1" to $GITHUB_OUTPUT when the update workflow should be re-triggered, and exits 1
(so GitHub emails the repo owner) when the site has been stale for a long time.

    SITE_DATA_URL=https://<you>.github.io/salmons-fpl/data.json python3 scripts/watchdog.py
"""
import datetime as dt
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fpl  # noqa: E402

MATCH_LIMIT = dt.timedelta(minutes=40)   # during a match window
QUIET_LIMIT = dt.timedelta(minutes=110)  # the rest of the time
ALERT_LIMIT = dt.timedelta(hours=4)      # fail loudly beyond this

now = dt.datetime.now(dt.timezone.utc)
url = os.environ["SITE_DATA_URL"]


def parse(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


try:
    req = urllib.request.Request(f"{url}?t={int(now.timestamp())}", headers={"User-Agent": fpl.UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        updated = parse(json.loads(r.read())["meta"]["updated"])
except Exception as e:  # noqa: BLE001
    print(f"Couldn't read the live site ({e}) - treating it as stale")
    updated = now - ALERT_LIMIT

in_match = False
try:
    for f in fpl.main("fixtures/"):
        ko = f.get("kickoff_time")
        if ko and parse(ko) - dt.timedelta(minutes=20) <= now <= parse(ko) + dt.timedelta(hours=3):
            in_match = True
            break
except Exception as e:  # noqa: BLE001
    print(f"Couldn't read fixtures ({e})")

age = now - updated
limit = MATCH_LIMIT if in_match else QUIET_LIMIT
stale = age > limit
print(f"Site data is {int(age.total_seconds() // 60)} min old; limit {int(limit.total_seconds() // 60)} min "
      f"({'match window' if in_match else 'quiet'}). {'STALE - re-triggering the update' if stale else 'OK'}")
if os.environ.get("GITHUB_OUTPUT"):
    with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
        fh.write(f"stale={1 if stale else 0}\n")
if age > ALERT_LIMIT:
    print("::error::The site has not updated for over 4 hours. Check the 'Update site' runs in the Actions tab.")
    sys.exit(1)
