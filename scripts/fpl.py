"""Small cached client for the FPL Draft and main FPL APIs.

- Every response is written to data/cache/ so a failed request falls back to the last good copy.
- `permanent=True` means "this can never change again" (e.g. a finished gameweek): served from cache forever.
- `max_age` (seconds) serves a cached copy if it is younger than that; 0 means always refetch.
- Requests are spaced at least 0.5s apart.
"""
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache"
DRAFT = "https://draft.premierleague.com/api/"
MAIN = "https://fantasy.premierleague.com/api/"
UA = "Mozilla/5.0 (compatible; league-stats-site/1.0)"
GAP = 0.5

_last = [0.0]
stats = {"fetched": 0, "cached": 0}


def _key(base, path):
    tag = "d" if base == DRAFT else "m"
    return CACHE / (tag + "_" + path.strip("/").replace("/", "_") + ".json")


def _get(base, path, max_age=0, permanent=False):
    CACHE.mkdir(parents=True, exist_ok=True)
    f = _key(base, path)
    if f.exists() and (permanent or (max_age and time.time() - f.stat().st_mtime < max_age)):
        stats["cached"] += 1
        return json.loads(f.read_text())
    err = None
    for attempt in range(3):
        wait = GAP - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        try:
            req = urllib.request.Request(base + path, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read()
            _last[0] = time.time()
            data = json.loads(body)
            f.write_text(json.dumps(data, separators=(",", ":")))
            stats["fetched"] += 1
            return data
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, ConnectionError) as e:
            _last[0] = time.time()
            err = e
            if isinstance(e, urllib.error.HTTPError) and e.code == 404:
                break
            time.sleep(1.5 * (attempt + 1))
    if f.exists():
        print(f"  ! {path}: {err} - using cached copy")
        return json.loads(f.read_text())
    raise RuntimeError(f"Could not fetch {base}{path}: {err}")


def draft(path, **kw):
    return _get(DRAFT, path, **kw)


def main(path, **kw):
    return _get(MAIN, path, **kw)
