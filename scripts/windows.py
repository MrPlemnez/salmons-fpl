"""When is FPL likely to be changing data? Shared by build.py (the update gate) and watchdog.py.

FPL changes data at a few predictable points, and the site should refresh often around each:
  - matches:    live scores, from 20 minutes before a kickoff to 3 hours after it
  - finalising: after a gameweek's last match, until FPL confirms the final points (bonus,
                auto-subs, Opta corrections). Since 2026/27 this is ~09:00 UK the next morning.
  - waivers:    from the waiver deadline until FPL has processed the claims
  - deadlines:  the hour after the trade and team deadlines (trades processed, squads locked)

busy() returns a short reason string, or None when FPL is quiet.
"""
import datetime as dt

import fpl


def _t(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def busy(now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    fixtures = fpl.main("fixtures/", max_age=600)
    for f in fixtures:
        ko = _t(f.get("kickoff_time"))
        if ko and ko - dt.timedelta(minutes=20) <= now <= ko + dt.timedelta(hours=3):
            return "match window"

    game = fpl.draft("game")
    cur = game.get("current_event")
    if cur:
        gw_fx = [f for f in fixtures if f.get("event") == cur]
        all_played = gw_fx and all(f.get("finished") or f.get("finished_provisional") for f in gw_fx)
        mboot = fpl.main("bootstrap-static/", max_age=600)
        checked = any(e["id"] == cur and e.get("data_checked") for e in mboot["events"])
        last_ko = max((_t(f["kickoff_time"]) for f in gw_fx if f.get("kickoff_time")), default=None)
        recent = last_ko and now <= last_ko + dt.timedelta(hours=48)
        if all_played and recent and not (game.get("current_event_finished") and checked):
            return f"waiting for FPL to confirm GW{cur} points"

    dboot = fpl.draft("bootstrap-static", max_age=3600)
    nxt = game.get("next_event")
    ev = next((e for e in dboot["events"]["data"] if e["id"] == nxt), {})
    waivers = _t(ev.get("waivers_time"))
    if waivers and waivers <= now <= waivers + dt.timedelta(hours=6) and not game.get("waivers_processed"):
        return "waiting for waivers to process"
    for key in ("waivers_time", "trades_time", "deadline_time"):
        t = _t(ev.get(key))
        if t and t <= now <= t + dt.timedelta(hours=1):
            return key.replace("_time", "") + " just passed"
    return None
