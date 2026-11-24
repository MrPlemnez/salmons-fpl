#!/usr/bin/env python3
"""Fetch league data and build site/data.json.

    python3 scripts/build.py            # normal run
    python3 scripts/build.py --gate     # exit early unless a match window is on or it's the top of the hour
    python3 scripts/build.py --rewrite N  # regenerate the write-ups for gameweek N
"""
import argparse
import datetime as dt
import json
import os
import sys
import urllib.request
from collections import defaultdict
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fpl  # noqa: E402
import projections  # noqa: E402
import writeups  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
CONFIG = json.loads((ROOT / "config.json").read_text())
HISTORY_FILE = ROOT / "history.json"
LID = CONFIG["league_id"]
POS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
UTC = dt.timezone.utc

# "Who needs what": how many fit, regularly playing players a squad wants at each position.
NEEDS_TARGET = {1: 1, 2: 4, 3: 4, 4: 2}
DEFCON_THRESHOLD = {2: 10, 3: 12, 4: 12}


def now():
    return dt.datetime.now(UTC)


def parse_time(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


# --------------------------------------------------------------------------- helpers

def best_xi(players, score):
    """players: iterable of (pid, pos). score: pid -> number.
    Returns (total, [pid, ...] in GK/DEF/MID/FWD order, "d-m-f") for the best valid formation."""
    by = {p: sorted([x for x in players if x[1] == p], key=lambda x: -score(x[0])) for p in POS}
    best = None
    for d in range(3, 6):
        for m in range(2, 6):
            f = 10 - d - m
            if not 1 <= f <= 3:
                continue
            if len(by[1]) < 1 or len(by[2]) < d or len(by[3]) < m or len(by[4]) < f:
                continue
            xi = by[1][:1] + by[2][:d] + by[3][:m] + by[4][:f]
            tot = sum(score(x[0]) for x in xi)
            if best is None or tot > best[0] + 1e-9:
                best = (tot, [x[0] for x in xi], f"{d}-{m}-{f}")
    return best or (0, [], "")


def bonus_from_bps(rows):
    """rows: [{'element', 'value'}] for one fixture -> {element: provisional bonus} (3/2/1 with FPL tie rules)."""
    groups = defaultdict(list)
    for r in rows:
        groups[r["value"]].append(r["element"])
    out, idx, awards = {}, 0, [3, 2, 1]
    for v in sorted(groups, reverse=True):
        if idx >= 3:
            break
        for el in groups[v]:
            out[el] = awards[idx]
        idx += len(groups[v])
    return out


def r1(x):
    return round(x, 1)


# --------------------------------------------------------------------------- main build

def build(args):
    t0 = now()
    issues = []

    def section_failed(name, e):
        import traceback
        traceback.print_exc()
        issues.append(f"{name} failed: {type(e).__name__}: {e}")
        print(f"  ! {name} section failed - publishing everything else")

    dboot = fpl.draft("bootstrap-static", max_age=240)
    game = fpl.draft("game")
    details = fpl.draft(f"league/{LID}/details")
    estatus = fpl.draft(f"league/{LID}/element-status")
    choices = fpl.draft(f"draft/{LID}/choices", max_age=86400)
    tx = fpl.draft(f"draft/league/{LID}/transactions")
    trades_raw = fpl.draft(f"draft/league/{LID}/trades")
    mboot = fpl.main("bootstrap-static/", max_age=240)
    mfix = fpl.main("fixtures/")

    current = game["current_event"] or 0
    cur_done = bool(game["current_event_finished"])
    last_done = current if cur_done else current - 1
    data_checked = {e["id"]: e["data_checked"] for e in mboot["events"]}
    events = {e["id"]: e for e in dboot["events"]["data"]}

    # ---------------- managers
    cfg_by_eid = {m["entry_id"]: m for m in CONFIG["managers"]}
    managers, le_to_eid = [], {}
    for le in details["league_entries"]:
        eid = le["entry_id"]
        c = cfg_by_eid.get(eid, {})
        le_to_eid[le["id"]] = eid
        managers.append({
            "id": eid, "le": le["id"],
            "name": c.get("name") or le["player_first_name"].title(),
            "nick": c.get("nickname") or c.get("name") or le["player_first_name"].title(),
            "full": f'{le["player_first_name"].title()} {le["player_last_name"].title()}',
            "team": le["entry_name"].replace("’", "'"),
            "ini": c.get("initials") or le["short_name"].upper(),
            "col": c.get("colour", "#777777"),
            "me": eid == CONFIG.get("me_entry_id"),
            "champ": eid == CONFIG.get("last_season_champion_entry_id"),
            "waiver": le.get("waiver_pick"),
        })
    eids = [m["id"] for m in managers]
    mname = {m["id"]: m["name"] for m in managers}

    histories = {eid: fpl.draft(f"entry/{eid}/history") for eid in eids}
    live, picks = {}, {}
    for g in range(1, current + 1):
        # Only freeze a gameweek once FPL has confirmed it (data_checked). Before that, auto-subs and
        # bonus can still change even though the gameweek is flagged finished.
        locked = bool((g < current or cur_done) and data_checked.get(g))
        live[g] = fpl.draft(f"event/{g}/live", permanent=locked)
        for eid in eids:
            picks[(eid, g)] = fpl.draft(f"entry/{eid}/event/{g}", permanent=locked)
    print(f"  {fpl.stats['fetched']} fetched, {fpl.stats['cached']} from cache")

    # ---------------- teams & fixtures
    teams = {t["id"]: {"s": t["short_name"], "n": t["name"]} for t in dboot["teams"]}
    team_fx = defaultdict(lambda: defaultdict(list))  # team -> gw -> [fixture view]
    fx_by_gw = defaultdict(list)
    for f in mfix:
        if not f.get("event"):
            continue
        g = f["event"]
        fx_by_gw[g].append(f)
        team_fx[f["team_h"]][g].append({"opp": f["team_a"], "h": 1, "fdr": f["team_h_difficulty"], "ko": f["kickoff_time"]})
        team_fx[f["team_a"]][g].append({"opp": f["team_h"], "h": 0, "fdr": f["team_a_difficulty"], "ko": f["kickoff_time"]})

    upcoming = [g for g in range(current + 1, current + 1 + projections.WEEKS) if g <= 38]

    # ---------------- players
    m_by_code = {e["code"]: e for e in mboot["elements"]}
    owner_now = {s["element"]: s["owner"] for s in estatus["element_status"]}
    players = {}
    for e in dboot["elements"]:
        m = m_by_code.get(e["code"], {})
        cop = e.get("chance_of_playing_next_round")
        if cop is None:
            cop = m.get("chance_of_playing_next_round")
        players[e["id"]] = {
            "id": e["id"], "name": e["web_name"], "pos": e["element_type"], "team": e["team"],
            "status": e["status"], "news": e.get("news") or "", "cop": cop,
            "total": e["total_points"], "minutes": e["minutes"],
            "ep_next": float(m["ep_next"]) if m.get("ep_next") not in (None, "") else None,
            "ppg": float(e.get("points_per_game") or 0), "form": float(e.get("form") or 0),
            "gw": {}, "mins": {}, "dc": {}, "stats": {},
        }

    # per-gameweek stats from /event/{gw}/live (+ provisional bonus for unfinished fixtures)
    prov_bonus = {}
    for g, lv in live.items():
        if g == current and not cur_done:
            for fx in lv.get("fixtures", []):
                if not fx.get("started"):
                    continue
                st = {s["s"]: s for s in fx.get("stats", [])}
                if st.get("bonus") and (st["bonus"]["h"] or st["bonus"]["a"]):
                    continue
                bps = st.get("bps")
                if bps:
                    prov_bonus.update(bonus_from_bps(bps["h"] + bps["a"]))
        for pid_s, el in lv["elements"].items():
            pid = int(pid_s)
            p = players.get(pid)
            if not p:
                continue
            s = el["stats"]
            pts = s["total_points"]
            if g == current and not cur_done:
                pts += prov_bonus.get(pid, 0)
            p["gw"][g] = pts
            p["mins"][g] = s["minutes"]
            p["dc"][g] = s.get("defensive_contribution", 0)
            p["stats"][g] = {k: s.get(k, 0) for k in ("goals_scored", "assists", "clean_sheets", "goals_conceded",
                                                     "saves", "bonus", "yellow_cards", "red_cards", "own_goals",
                                                     "penalties_saved", "penalties_missed", "defensive_contribution",
                                                     "minutes")}
            if g == current and not cur_done and pid in prov_bonus:
                p["stats"][g]["bonus_prov"] = prov_bonus[pid]

    def gpts(pid, g):
        return players[pid]["gw"].get(g, 0) if pid in players else 0

    def gmins(pid, g):
        return players[pid]["mins"].get(g, 0) if pid in players else 0

    done_gws = list(range(1, last_done + 1))

    def recent_minutes(pid, n=5):
        gws = done_gws[-n:]
        return [gmins(pid, g) for g in gws]

    for pid, p in players.items():
        p["proj"] = projections.project(p, team_fx[p["team"]], upcoming, recent_minutes(pid))
        p["pw"] = r1(sum(p["proj"]) / len(p["proj"])) if p["proj"] else 0.0
        apps = [g for g in done_gws if gmins(pid, g) > 0]
        tot_dc = sum(p["dc"].get(g, 0) for g in done_gws)
        p["dc90"] = r1(tot_dc / p["minutes"] * 90) if p["minutes"] else 0.0
        thr = DEFCON_THRESHOLD.get(p["pos"])
        p["dchit"] = bool(thr and apps and sum(1 for g in apps if p["dc"].get(g, 0) >= thr) / len(apps) >= 0.5)
        p["dead"] = p["status"] in ("i", "s", "u", "n") or p["minutes"] < 180
        p["fit"] = (p["status"] == "a" or (p["status"] == "d" and (p["cop"] or 0) >= 75)) and not p["dead"]
        last3 = done_gws[-3:]
        p["regular"] = sum(1 for g in last3 if gmins(pid, g) > 0) >= min(2, len(last3))

    # ---------------- squads per gameweek, scorers, bench
    def squad(eid, g):
        return [pk["element"] for pk in picks[(eid, g)]["picks"]]

    def lineup(eid, g):
        """Returns (scorers, bench, subs_in, subs_out) for a gameweek. For the live gameweek, simulates auto-subs."""
        pk = sorted(picks[(eid, g)]["picks"], key=lambda x: x["position"])
        starters = [x["element"] for x in pk if x["position"] <= 11]
        bench = [x["element"] for x in pk if x["position"] > 11]
        subs = picks[(eid, g)].get("subs") or []
        if subs:
            # The API has already applied these: subs-in sit in positions 1-11, subs-out on the bench.
            s_in = [s["element_in"] for s in subs]
            s_out = [s["element_out"] for s in subs]
            return starters, [x for x in bench if x not in s_out], s_in, s_out
        if g == current and not cur_done:
            s_in, s_out = simulate_subs(starters, bench, g)
            return ([x for x in starters if x not in s_out] + s_in, [x for x in bench if x not in s_in], s_in, s_out)
        return starters, bench, [], []

    def team_done(team, g):
        fxs = [f for f in fx_by_gw[g] if team in (f["team_h"], f["team_a"])]
        return all(f.get("finished") or f.get("finished_provisional") for f in fxs)

    def simulate_subs(starters, bench, g):
        xi = list(starters)
        s_in, s_out = [], []
        for st in starters:
            p = players.get(st)
            if not p or gmins(st, g) > 0 or not team_done(p["team"], g):
                continue
            for b in bench:
                if b in s_in:
                    continue
                bp = players.get(b)
                if not bp or gmins(b, g) == 0:
                    continue
                if (p["pos"] == 1) != (bp["pos"] == 1):
                    continue
                trial = [x for x in xi if x != st] + [b]
                cnt = defaultdict(int)
                for x in trial:
                    cnt[players[x]["pos"]] += 1
                if cnt[2] >= 3 and cnt[3] >= 2 and cnt[4] >= 1:
                    xi = trial
                    s_in.append(b)
                    s_out.append(st)
                    break
        return s_in, s_out

    owner_at = defaultdict(dict)  # gw -> pid -> eid
    for (eid, g), pk in picks.items():
        for x in pk["picks"]:
            owner_at[g][x["element"]] = eid

    # ---------------- gameweek scores & standings by gameweek
    score = {eid: {} for eid in eids}
    for eid, h in histories.items():
        for row in h["history"]:
            if row["event"] <= last_done:
                score[eid][row["event"]] = row["points"]
    lineups = {(eid, g): lineup(eid, g) for eid in eids for g in range(1, current + 1)}
    live_scores = {}
    if current and not cur_done:
        for eid in eids:
            live_scores[eid] = sum(gpts(x, current) for x in lineups[(eid, current)][0])

    cum, rank_at = {eid: {} for eid in eids}, {}
    for g in done_gws:
        for eid in eids:
            cum[eid][g] = cum[eid].get(g - 1, 0) + score[eid].get(g, 0)
        order = sorted(eids, key=lambda e: -cum[e][g])
        rank_at[g] = {}
        for i, e in enumerate(order):
            prev = order[i - 1] if i else None
            rank_at[g][e] = rank_at[g][prev] if prev and cum[prev][g] == cum[e][g] else i + 1

    # ---------------- verification against the league's own standings
    st_by_eid = {le_to_eid[s["league_entry"]]: s for s in details["standings"]}
    for eid in eids:
        api_total = st_by_eid[eid]["total"]
        mine = cum[eid].get(last_done, 0)
        if cur_done and api_total != mine:
            issues.append(f"{mname[eid]}: league total {api_total} vs summed history {mine}")
        for g in done_gws:
            calc = sum(gpts(x, g) for x in lineups[(eid, g)][0])
            if calc != score[eid].get(g, 0):
                issues.append(f"{mname[eid]} GW{g}: history {score[eid].get(g)} vs players {calc}")
                # Self-heal: drop the cached copies so the next run refetches this gameweek.
                fpl.forget(f"entry/{eid}/event/{g}")
                fpl.forget(f"event/{g}/live")
    print("Verification:", "all totals and gameweek scores match" if not issues else f"{len(issues)} mismatches")
    for i in issues[:20]:
        print("  -", i)

    # ---------------- standings (after last finished gameweek)
    standings = []
    if last_done:
        lead = max(cum[e][last_done] for e in eids)
        for eid in sorted(eids, key=lambda e: rank_at[last_done][e]):
            prev = rank_at.get(last_done - 1, {}).get(eid)
            rk = rank_at[last_done][eid]
            standings.append({"id": eid, "rank": rk, "prev": prev, "move": (prev - rk) if prev else 0,
                              "gw": score[eid].get(last_done, 0), "total": cum[eid][last_done],
                              "gap": cum[eid][last_done] - lead})

    # ---------------- awards per finished gameweek
    gw_data, season_awards = {}, {eid: {"motw": 0, "stinker": 0, "bench": 0} for eid in eids}
    for g in done_gws:
        sc = {eid: score[eid].get(g, 0) for eid in eids}
        hi, lo = max(sc.values()), min(sc.values())
        motw = [e for e in eids if sc[e] == hi]
        stink = [e for e in eids if sc[e] == lo]
        bench_pts = {eid: sum(gpts(x, g) for x in lineups[(eid, g)][1]) for eid in eids}
        bmax = max(bench_pts.values())
        bench_w = [e for e in eids if bench_pts[e] == bmax] if bmax > 0 else []
        for e in motw:
            season_awards[e]["motw"] += 1
        for e in stink:
            season_awards[e]["stinker"] += 1
        for e in bench_w:
            season_awards[e]["bench"] += 1

        jams = [(gpts(x, g), x, eid, lineups[(eid, g)][3][i])
                for eid in eids for i, x in enumerate(lineups[(eid, g)][2])]
        jam = max(jams) if jams else None
        starters_all = [(gpts(x, g), x, eid) for eid in eids for x in lineups[(eid, g)][0]]
        red = min(starters_all, key=lambda t: (t[0], -players[t[1]]["stats"].get(g, {}).get("red_cards", 0))) if starters_all else None
        keepers = [t for t in starters_all if players[t[1]]["pos"] == 1 and gmins(t[1], g) > 0]
        gloves = min(keepers) if keepers else None

        owned = [(pid, players[pid]["pos"]) for pid in owner_at[g] if pid in players]
        tot, xi, form = best_xi(owned, lambda pid: gpts(pid, g))

        prev_rank = rank_at.get(g - 1, {})
        moves = {e: (prev_rank[e] - rank_at[g][e]) if prev_rank else 0 for e in eids}
        gw_data[g] = {
            "scores": sc, "bench": bench_pts, "rank": rank_at[g], "move": moves,
            "awards": {
                "motw": {"ids": motw, "pts": hi},
                "stinker": {"ids": stink, "pts": lo},
                "bench": {"ids": bench_w, "pts": bmax,
                          "players": {e: [x for x in lineups[(e, g)][1] if gpts(x, g) > 0] for e in bench_w}},
                "bench_jam": {"id": jam[2], "pid": jam[1], "pts": jam[0], "for": jam[3]} if jam and jam[0] >= 4 else None,
                "red_card": {"id": red[2], "pid": red[1], "pts": red[0]} if red else None,
                "gloves": {"id": gloves[2], "pid": gloves[1], "pts": gloves[0]} if gloves else None,
            },
            "xi": {"formation": form, "total": tot,
                   "players": [{"pid": pid, "owner": owner_at[g][pid], "pts": gpts(pid, g)} for pid in xi]},
        }

    # ---------------- write-ups (once a gameweek is final and bonus is confirmed)
    try:
        results_by_gw = {}
        for g in done_gws:
            results_by_gw[g] = [f"{teams[f['team_h']]['n']} {f['team_h_score']}-{f['team_a_score']} {teams[f['team_a']]['n']}"
                                for f in sorted(fx_by_gw[g], key=lambda f: f["kickoff_time"] or "") if f.get("finished")]
        tx_by_gw = defaultdict(lambda: defaultdict(list))
        for t in tx["transactions"]:
            if t["result"] == "a":
                tx_by_gw[t["event"]][t["entry"]].append(t)

        wu_all = {}
        for g in done_gws:
            if not data_checked.get(g):
                continue
            facts = writeup_facts(g, gw_data[g], managers, players, teams, results_by_gw[g], lineups, tx_by_gw[g],
                                  cum, standings_at=rank_at)
            wu_all[g] = writeups.get(g, facts, force=(args.rewrite == g))
        overrides = writeups.overrides()
        for g, w in wu_all.items():
            gw_data[g]["writeup"] = writeups.apply_overrides(w, overrides.get(str(g), {}))
    except Exception as e:  # one broken section must never stop the site updating
        section_failed("write-ups", e)

    # ---------------- snapshots
    try:
        snapdir = ROOT / "snapshots"
        snapdir.mkdir(exist_ok=True)
        for g in done_gws:
            f = snapdir / f"gw{g:02d}.json"
            if not f.exists() and data_checked.get(g):
                f.write_text(json.dumps({"gw": g, "saved": now().isoformat(),
                                         "table": [{"id": e, "name": mname[e], "rank": rank_at[g][e], "gw": score[e].get(g, 0),
                                                    "total": cum[e][g]} for e in sorted(eids, key=lambda e: rank_at[g][e])]},
                                        indent=1))
    except Exception as e:  # one broken section must never stop the site updating
        section_failed("snapshots", e)

    # ---------------- current squads (element-status owner)
    squads = {eid: [pid for pid, o in owner_now.items() if o == eid and pid in players] for eid in eids}

    def proj_best(pids, i):
        return best_xi([(p, players[p]["pos"]) for p in pids], lambda p: players[p]["proj"][i] if players[p]["proj"] else 0)

    def proj_week(pids):
        if not upcoming:
            return 0.0
        return sum(proj_best(pids, i)[0] for i in range(len(upcoming))) / len(upcoming)

    squads_out = {}
    for eid in eids:
        pids = squads[eid]
        tot, xi, form = best_xi([(p, players[p]["pos"]) for p in pids], lambda p: players[p]["total"])
        bench = sorted([p for p in pids if p not in xi], key=lambda p: (players[p]["pos"] != 1, -players[p]["total"]))
        squads_out[eid] = {
            "xi": xi, "bench": bench, "formation": form, "xi_pts": tot,
            "squad_pts": sum(players[p]["total"] for p in pids),
            "bench_pts": sum(players[p]["total"] for p in bench),
            "unavailable": sum(1 for p in pids if players[p]["status"] in ("i", "s", "u", "n")),
            "dead": sum(1 for p in pids if players[p]["dead"]),
        }

    # ---------------- power rankings
    power, league_avg3 = [], 0.0
    try:
        league_last3 = [sum(score[e].get(g, 0) for g in done_gws[-3:]) / max(1, len(done_gws[-3:])) for e in eids]
        league_avg3 = sum(league_last3) / len(eids) if eids else 0
        table_rank = {s["id"]: s["rank"] for s in standings}
        power = []
        for eid in eids:
            pids = squads[eid]
            pw = proj_week(pids)
            top2 = sorted(pids, key=lambda p: -players[p]["pw"])[:2]
            core = sorted(pids, key=lambda p: -players[p]["total"])[:11]
            missing = [p for p in core if players[p]["status"] in ("i", "s", "u", "n") or (players[p]["cop"] is not None and players[p]["cop"] < 50)]
            last3 = sum(score[eid].get(g, 0) for g in done_gws[-3:]) / max(1, len(done_gws[-3:]))
            power.append({"id": eid, "proj": r1(pw), "top": top2, "missing": missing, "last3": r1(last3)})
        power.sort(key=lambda x: -x["proj"])
        for i, p in enumerate(power):
            p["rank"] = i + 1
            p["vs_table"] = table_rank.get(p["id"], i + 1) - (i + 1)
    except Exception as e:  # one broken section must never stop the site updating
        section_failed("power rankings", e)

    # ---------------- needs
    pos_points = {eid: {1: 0, 2: 0, 3: 0, 4: 0} for eid in eids}
    who_needs = {eid: {p: {'fit': 0, 'held': 0, 'shade': 'g'} for p in POS} for eid in eids}
    try:
        pos_points = {}
        for eid in eids:
            acc = {1: 0, 2: 0, 3: 0, 4: 0}
            for g in done_gws:
                for x in lineups[(eid, g)][0]:
                    if x in players:
                        acc[players[x]["pos"]] += gpts(x, g)
            pos_points[eid] = acc
        who_needs = {}
        for eid in eids:
            row = {}
            for pos in POS:
                held = [p for p in squads[eid] if players[p]["pos"] == pos]
                fit = [p for p in held if players[p]["fit"] and players[p]["regular"]]
                target = NEEDS_TARGET[pos]
                shade = "g" if len(fit) >= target else ("a" if len(fit) == target - 1 else "r")
                row[pos] = {"fit": len(fit), "held": len(held), "shade": shade}
            who_needs[eid] = row
    except Exception as e:  # one broken section must never stop the site updating
        section_failed("needs", e)

    # ---------------- waiver wire
    wire = sorted([pid for pid, o in owner_now.items() if o is None and pid in players
                   and players[pid]["status"] not in ("u", "n")],
                  key=lambda p: (-players[p]["pw"], -players[p]["total"]))

    # ---------------- trades (follow each squad slot through later waiver swaps)
    trades_out, trade_rows = [], []
    acc_tx = sorted([t for t in tx["transactions"] if t["result"] == "a"], key=lambda t: (t["event"], t["added"]))
    done_trades = sorted([t for t in trades_raw.get("trades", []) if t["state"] == "p"],
                         key=lambda t: t.get("response_time") or "", reverse=True)
    try:

        def follow(eid, pid, start):
            chain, pts, holder = [pid], 0, pid
            for g in range(start, last_done + 1):
                sq = squad(eid, g)
                if holder not in sq:
                    nxt = next((t for t in acc_tx if t["entry"] == eid and t["element_out"] == holder
                                and t["event"] <= g and t["element_in"] in sq), None)
                    if not nxt:
                        holder = None
                        break
                    holder = nxt["element_in"]
                    chain.append(holder)
                pts += gpts(holder, g)
            still = holder is not None and owner_now.get(holder) == eid
            future = sum(players[holder]["proj"]) if still and holder in players else 0
            return {"chain": chain, "pts": pts, "proj": r1(future), "value": r1(pts + future), "kept": still}

        trades_out, trade_table = [], {eid: {"won": 0, "lost": 0, "net": 0.0} for eid in eids}
        for t in done_trades:
            a, b, g0 = t["offered_entry"], t["received_entry"], t["event"]
            a_gets = [follow(a, it["element_in"], g0) for it in t["tradeitem_set"]]
            b_gets = [follow(b, it["element_out"], g0) for it in t["tradeitem_set"]]
            va, vb = sum(x["value"] for x in a_gets), sum(x["value"] for x in b_gets)
            margin = r1(va - vb)
            winner = a if margin >= 3 else (b if margin <= -3 else None)
            if winner:
                loser = b if winner == a else a
                trade_table[winner]["won"] += 1
                trade_table[loser]["lost"] += 1
            trade_table[a]["net"] += margin
            trade_table[b]["net"] -= margin
            trades_out.append({"gw": g0, "time": t.get("response_time"), "a": a, "b": b,
                               "a_gets": a_gets, "b_gets": b_gets, "va": r1(va), "vb": r1(vb), "winner": winner})
        trade_rows = sorted([{"id": e, **v, "net": r1(v["net"])} for e, v in trade_table.items()
                             if v["won"] or v["lost"] or v["net"]], key=lambda r: -r["net"])
    except Exception as e:  # one broken section must never stop the site updating
        section_failed("trades", e)

    # ---------------- swap shop: 1-for-1 and 2-for-2 like-for-like trades where both best XIs improve
    swaps = []
    try:
        base_pw = {eid: proj_week(squads[eid]) for eid in eids}
        swaps = []
        for a, b in combinations(eids, 2):
            found = []
            for na in (1, 2):
                for ga in combinations(squads[a], na):
                    pos_a = sorted(players[p]["pos"] for p in ga)
                    if any(players[p]["status"] in ("u", "n") for p in ga):
                        continue
                    for gb in combinations(squads[b], na):
                        if sorted(players[p]["pos"] for p in gb) != pos_a:
                            continue
                        if na == 2 and pos_a[0] == pos_a[1]:
                            continue
                        new_a = [p for p in squads[a] if p not in ga] + list(gb)
                        new_b = [p for p in squads[b] if p not in gb] + list(ga)
                        da = proj_week(new_a) - base_pw[a]
                        db = proj_week(new_b) - base_pw[b]
                        if da > 0.2 and db > 0.2:
                            found.append({"a": a, "b": b, "a_gives": list(ga), "b_gives": list(gb),
                                          "a_gain": r1(da), "b_gain": r1(db), "score": min(da, db)})
            found.sort(key=lambda s: -s["score"])
            swaps.extend(found[:1])
        swaps.sort(key=lambda s: -s["score"])
        swaps = swaps[:14]
        for s in swaps:
            s.pop("score", None)
    except Exception as e:  # one broken section must never stop the site updating
        section_failed("swap shop", e)

    # ---------------- records (this season)
    rec = {}
    try:
        rec = {}
        if done_gws:
            allsc = [(score[e].get(g, 0), e, g) for e in eids for g in done_gws]
            hi = max(allsc)
            lo = min(allsc)
            margins = []
            for g in done_gws:
                s = sorted(((score[e].get(g, 0), e) for e in eids), reverse=True)
                margins.append((s[0][0] - s[1][0], s[0][1], g))
            mg = max(margins)
            bmax = max(((gw_data[g]["bench"][e], e, g) for e in eids for g in done_gws))
            tcount = defaultdict(int)
            for t in done_trades:
                tcount[t["offered_entry"]] += 1
                tcount[t["received_entry"]] += 1
            xcount = defaultdict(int)
            for t in acc_tx:
                xcount[t["entry"]] += 1
            rec = {
                "high": {"v": hi[0], "id": hi[1], "gw": hi[2]},
                "low": {"v": lo[0], "id": lo[1], "gw": lo[2]},
                "margin": {"v": mg[0], "id": mg[1], "gw": mg[2]},
                "bench": {"v": bmax[0], "id": bmax[1], "gw": bmax[2]},
                "trades": ({"v": max(tcount.values()), "ids": [e for e in eids if tcount[e] == max(tcount.values())]}
                           if tcount else None),
                "transfers": {"v": max(xcount.values()), "ids": [e for e in eids if xcount[e] == max(xcount.values())]}
                if xcount else None,
                "hauls": [{"pts": p, "pid": x, "id": e, "gw": g} for p, x, e, g in
                          sorted(((gpts(x, g), x, e, g) for e in eids for g in done_gws for x in lineups[(e, g)][0]),
                                 key=lambda t: (-t[0], t[3]))[:10]],
                "bench_disasters": [{"pts": p, "pid": x, "id": e, "gw": g} for p, x, e, g in
                                    sorted(((gpts(x, g), x, e, g) for e in eids for g in done_gws for x in lineups[(e, g)][1]),
                                           key=lambda t: (-t[0], t[3]))[:10]],
            }
    except Exception as e:  # one broken section must never stop the site updating
        section_failed("records", e)

    # ---------------- past seasons / all time
    seasons, alltime = [], {'titles': {}}
    try:
        hist = json.loads(HISTORY_FILE.read_text()) if HISTORY_FILE.exists() else {"seasons": []}
        seasons = sorted(hist.get("seasons", []), key=lambda s: s["season"])
        if last_done == 38 and cur_done and not any(s["season"] == CONFIG["season"] for s in seasons):
            seasons.append({"season": CONFIG["season"], "champion": mname[standings[0]["id"]],
                            "table": [{"name": mname[s["id"]], "total": s["total"]} for s in standings]})
        alltime = all_time_records(seasons)
    except Exception as e:  # one broken section must never stop the site updating
        section_failed("past seasons", e)

    # ---------------- draft board
    draft_out, draft_order, rounds, best_value, misses, draft_dt = [], [], 0, [], [], None
    try:
        picks_list = sorted(choices["choices"], key=lambda c: c["index"])
        rank_by_points = {pid: i + 1 for i, pid in enumerate(sorted(players, key=lambda p: -players[p]["total"]))}
        draft_out = []
        for c in picks_list:
            pid, eid = c["element"], c["entry"]
            if pid not in players:
                continue
            for_him = sum(gpts(pid, g) for g in done_gws if pid in squad(eid, g))
            draft_out.append({"pick": c["pick"], "round": c["round"], "id": eid, "pid": pid,
                              "rank": rank_by_points[pid], "value": c["pick"] - rank_by_points[pid],
                              "kept": owner_now.get(pid) == eid, "for": for_him})
        draft_order = [c["entry"] for c in picks_list if c["round"] == 1]
        rounds = max((c["round"] for c in picks_list), default=0)
        best_value = sorted(draft_out, key=lambda d: -d["value"])[:10]
        early_cut = len(eids) * 6
        misses = sorted([d for d in draft_out if d["pick"] <= early_cut], key=lambda d: d["value"])[:10]
        draft_dt = details["league"].get("draft_dt")
    except Exception as e:  # one broken section must never stop the site updating
        section_failed("draft board", e)

    # ---------------- waivers: every round, plus a verdict on each completed move
    waivers = None
    try:
        # A move is judged over the same gameweeks for both players: from the first gameweek the new man
        # is in the squad until he leaves it (or now). In = his points, out = what the dropped man scored
        # over those weeks wherever he was. Hit at +3 or more, miss at -3 or worse (same as trades).
        def judge(t):
            eid, pin, pout, g0 = t["entry"], t["element_in"], t["element_out"], t["event"]
            window = []
            for g in range(g0, last_done + 1):
                if pin in squad(eid, g):
                    window.append(g)
                elif window:
                    break
            if not window:
                return {"gws": 0, "pin": 0, "pout": 0, "net": None, "counted": 0}
            pts_in = sum(gpts(pin, g) for g in window)
            pts_out = sum(gpts(pout, g) for g in window)
            counted = sum(gpts(pin, g) for g in window if pin in lineups[(eid, g)][0])
            return {"gws": len(window), "pin": pts_in, "pout": pts_out, "net": pts_in - pts_out, "counted": counted}

        moves = []
        for t in tx["transactions"]:
            if t["result"] != "a" or t["element_in"] not in players or t["element_out"] not in players:
                continue
            v = judge(t)
            moves.append({"id": t["entry"], "gw": t["event"], "k": t["kind"], "in": t["element_in"], "out": t["element_out"],
                          "time": t["added"], "kept": owner_now.get(t["element_in"]) == t["entry"], **v})
        moves.sort(key=lambda m: (m["gw"], m["time"] or ""))
        rounds = {}
        for t in sorted(tx["transactions"], key=lambda t: (t["event"], t.get("priority") or 0, t["added"] or "")):
            r = rounds.setdefault(t["event"], {"claims": [], "fa": []})
            if t["kind"] == "w":
                r["claims"].append({"id": t["entry"], "in": t["element_in"], "out": t["element_out"], "res": t["result"],
                                    "pri": t.get("priority")})
        for m in moves:
            if m["k"] == "f":
                rounds[m["gw"]]["fa"].append({"id": m["id"], "in": m["in"], "out": m["out"]})
        kings = []
        for eid in eids:
            mine = [m for m in moves if m["id"] == eid and m["net"] is not None]
            if not any(m["id"] == eid for m in moves):
                continue
            kings.append({"id": eid, "moves": sum(1 for m in moves if m["id"] == eid),
                          "hits": sum(1 for m in mine if m["net"] >= 3), "misses": sum(1 for m in mine if m["net"] <= -3),
                          "net": sum(m["net"] for m in mine), "counted": sum(m["counted"] for m in mine)})
        kings.sort(key=lambda k: -k["net"])
        judged = [m for m in moves if m["net"] is not None]
        waivers = {
            "rounds": {g: r for g, r in rounds.items()},
            "moves": moves,
            "kings": kings,
            "best": sorted(judged, key=lambda m: (-m["net"], -m["pin"]))[:8],
            "worst": sorted(judged, key=lambda m: (m["net"], m["pin"]))[:8],
            "latest": max(rounds) if rounds else None,
        } if rounds else None
    except Exception as e:  # one broken section must never stop the site updating
        section_failed("waivers", e)

    waiver_order = [m["id"] for m in sorted(managers, key=lambda m: m.get("waiver") or 99)]

    # ---------------- live / midweek view of the current gameweek
    live_out, is_live = None, False
    try:
        live_out = None
        if current:
            g = current
            rows = []
            for eid in eids:
                scorers, bench_left, s_in, s_out = lineups[(eid, g)]
                pk = sorted(picks[(eid, g)]["picks"], key=lambda x: x["position"])
                plist = []
                for x in pk:
                    pid = x["element"]
                    if pid not in players:
                        continue
                    st = players[pid]["stats"].get(g, {})
                    role = "in" if pid in s_in else ("out" if pid in s_out else ("xi" if x["position"] <= 11 else "bench"))
                    team = players[pid]["team"]
                    fxs = [f for f in fx_by_gw[g] if team in (f["team_h"], f["team_a"])]
                    state = "none" if not fxs else ("done" if team_done(team, g) else
                                                    ("live" if any(f.get("started") for f in fxs) else "pre"))
                    plist.append({"pid": pid, "pts": gpts(pid, g), "min": st.get("minutes", 0), "role": role,
                                  "bp": st.get("bonus_prov", 0), "b": st.get("bonus", 0), "yc": st.get("yellow_cards", 0),
                                  "rc": st.get("red_cards", 0), "g": st.get("goals_scored", 0), "a": st.get("assists", 0),
                                  "state": state})
                pts = live_scores.get(eid, score[eid].get(g, 0))
                prev_total = cum[eid].get(g - 1, 0)
                rows.append({"id": eid, "pts": pts, "total": prev_total + pts, "players": plist})
            rows.sort(key=lambda r: -r["total"])
            fixtures_g = [{"h": f["team_h"], "a": f["team_a"], "hs": f["team_h_score"], "as": f["team_a_score"],
                           "ko": f["kickoff_time"], "started": f.get("started"), "done": f.get("finished") or f.get("finished_provisional"),
                           "min": f.get("minutes")} for f in sorted(fx_by_gw[g], key=lambda f: f["kickoff_time"] or "")]
            live_out = {"gw": g, "final": cur_done, "checked": bool(data_checked.get(g)), "managers": rows, "fixtures": fixtures_g}
        is_live = bool(live_out and not cur_done and any(f["started"] and not f["done"] for f in live_out["fixtures"]))
    except Exception as e:  # one broken section must never stop the site updating
        section_failed("live view", e)

    # ---------------- preview of the next gameweek
    preview = None
    try:
        preview = None
        if upcoming:
            g = upcoming[0]
            rows = []
            for eid in eids:
                tot, xi, form = proj_best(squads[eid], 0)
                doubts = [{"pid": p, "news": players[p]["news"], "cop": players[p]["cop"]} for p in squads[eid]
                          if players[p]["status"] != "a" or (players[p]["cop"] is not None and players[p]["cop"] < 100)]
                rows.append({"id": eid, "proj": r1(tot), "formation": form, "xi": xi, "doubts": doubts})
            rows.sort(key=lambda r: -r["proj"])
            ev = events.get(g, {})
            preview = {"gw": g, "deadline": ev.get("deadline_time"), "managers": rows}
    except Exception as e:  # one broken section must never stop the site updating
        section_failed("preview", e)

    # ---------------- next deadline
    nxt = events.get(game.get("next_event") or 0) or {}

    # ---------------- assemble
    used = set()
    for eid in eids:
        used.update(squads[eid])
    for g in done_gws:
        used.update(owner_at[g].keys())
    used.update(wire[:400])
    used.update(d["pid"] for d in draft_out)
    for t in tx["transactions"]:
        used.update([t["element_in"], t["element_out"]])
    for t in trades_out:
        for x in t["a_gets"] + t["b_gets"]:
            used.update(x["chain"])
    gw_range = list(range(1, current + 1))
    pl_out = {}
    for pid in used:
        p = players.get(pid)
        if not p:
            continue
        pl_out[pid] = {"n": p["name"], "p": p["pos"], "t": p["team"], "s": p["status"], "news": p["news"],
                       "cop": p["cop"], "pts": p["total"], "min": p["minutes"],
                       "gw": [p["gw"].get(g, 0) for g in gw_range], "pr": p["proj"], "pw": p["pw"],
                       "dc90": p["dc90"], "dch": p["dchit"], "dead": p["dead"], "o": owner_now.get(pid)}

    fixtures_next = {}
    for tid in teams:
        fixtures_next[tid] = [{"gw": g, "o": f["opp"], "h": f["h"], "d": f["fdr"]}
                              for g in upcoming for f in team_fx[tid].get(g, [])]

    data = {
        "meta": {
            "app": CONFIG["app_name"], "sub": CONFIG.get("app_subtitle", ""), "season": CONFIG["season"],
            "league": details["league"]["name"], "updated": now().isoformat(), "after": last_done,
            "current": current, "final": cur_done, "live": is_live, "upcoming": upcoming,
            "next": {"gw": nxt.get("id"), "deadline": nxt.get("deadline_time"), "waivers": nxt.get("waivers_time"),
                     "trades": nxt.get("trades_time")},
            "me": CONFIG.get("me_entry_id"), "issues": issues[:10],
        },
        "managers": managers, "teams": teams, "players": pl_out, "fx": fixtures_next,
        "standings": standings,
        "scores": {eid: [score[eid].get(g) for g in done_gws] for eid in eids},
        "cum": {eid: [cum[eid][g] for g in done_gws] for eid in eids},
        "gws": gw_data, "season_awards": season_awards,
        "live": live_out, "preview": preview, "waivers": waivers, "waiver_order": waiver_order,
        "power": power, "league_avg3": r1(league_avg3),
        "squads": squads_out, "pos_points": pos_points, "needs": who_needs,
        "wire": [p for p in wire if p in pl_out],
        "trades": trades_out, "trade_table": trade_rows, "swaps": swaps,
        "records": rec, "alltime": alltime, "seasons": seasons,
        "draft": {"date": draft_dt, "rounds": rounds, "order": draft_order, "picks": draft_out,
                  "best": best_value, "misses": misses},
    }
    SITE.mkdir(exist_ok=True)
    out = SITE / "data.json"
    out.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False))
    print(f"Wrote {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB) in {(now() - t0).seconds}s. "
          f"After GW{last_done}, current GW{current} {'final' if cur_done else 'in progress'}.")
    return data


def writeup_facts(g, gd, managers, players, teams, results, lineups, txg, cum, standings_at):
    """Facts handed to the write-up generator. Everything in here is real data; nothing is inferred."""
    byid = {m["id"]: m for m in managers}

    def pl(pid):
        p = players[pid]
        st = p["stats"].get(g, {})
        return {"name": p["name"], "pos": POS[p["pos"]], "club": teams[p["team"]]["n"], "points": p["gw"].get(g, 0),
                "stats": {k: v for k, v in st.items() if v}}

    table = []
    for eid, rk in sorted(standings_at[g].items(), key=lambda kv: kv[1]):
        table.append({"manager": byid[eid]["nick"], "team": byid[eid]["team"], "rank": rk,
                      "moved": gd["move"][eid], "gw_points": gd["scores"][eid], "total": cum[eid][g]})
    team_sheets = {}
    for eid in gd["scores"]:
        sc, bench, s_in, s_out = lineups[(eid, g)]
        team_sheets[byid[eid]["nick"]] = {
            "scorers": [pl(x) for x in sorted(sc, key=lambda x: -players[x]["gw"].get(g, 0)) if x in players][:6],
            "bench_left": [pl(x) for x in bench if x in players],
            "auto_subs": [{"on": players[i]["name"], "off": players[o]["name"]} for i, o in zip(s_in, s_out)],
            "moves_this_gw": [{"in": players[t["element_in"]]["name"], "out": players[t["element_out"]]["name"],
                               "kind": "waiver" if t["kind"] == "w" else "free agent"}
                              for t in txg.get(eid, []) if t["element_in"] in players and t["element_out"] in players],
        }
    aw = gd["awards"]

    def who(ids):
        return [byid[e]["nick"] for e in ids]

    awards = {
        "manager_of_the_week": {"managers": who(aw["motw"]["ids"]), "points": aw["motw"]["pts"]},
        "stinker_of_the_week": {"managers": who(aw["stinker"]["ids"]), "points": aw["stinker"]["pts"]},
        "bench_of_the_week": {"managers": who(aw["bench"]["ids"]), "points_left_on_bench": aw["bench"]["pts"]},
        "bench_jam_of_the_week": ({"manager": byid[aw["bench_jam"]["id"]]["nick"], "player": pl(aw["bench_jam"]["pid"]),
                                   "came_on_for": players[aw["bench_jam"]["for"]]["name"]} if aw["bench_jam"] else None),
        "red_card_of_the_week": ({"manager": byid[aw["red_card"]["id"]]["nick"], "player": pl(aw["red_card"]["pid"])}
                                 if aw["red_card"] else None),
        "gloves_of_the_week": ({"manager": byid[aw["gloves"]["id"]]["nick"], "player": pl(aw["gloves"]["pid"])}
                               if aw["gloves"] else None),
    }
    xi = [{"element": x["pid"], "owner": byid[x["owner"]]["nick"], **pl(x["pid"])} for x in gd["xi"]["players"]]
    return {"gameweek": g, "premier_league_results": results, "league_table_after": table,
            "awards": awards, "team_of_the_week": {"formation": gd["xi"]["formation"], "players": xi},
            "team_sheets": team_sheets}


def all_time_records(seasons):
    full = [s for s in seasons if s.get("table") and not s.get("near_final")]
    out = {"titles": defaultdict(int)}
    for s in seasons:
        if s.get("champion"):
            out["titles"][s["champion"]] += 1
    out["titles"] = dict(out["titles"])
    if not full:
        return out
    rows = [(r["total"], r["name"], s["season"], i + 1) for s in full
            for i, r in enumerate(sorted(s["table"], key=lambda r: -r["total"]))]
    hi, lo = max(rows), min(rows)
    out["high"] = {"v": hi[0], "name": hi[1], "season": hi[2], "champ": hi[3] == 1}
    out["low"] = {"v": lo[0], "name": lo[1], "season": lo[2]}
    gaps = []
    for s in full:
        t = sorted(s["table"], key=lambda r: -r["total"])
        if len(t) > 1:
            gaps.append((t[0]["total"] - t[1]["total"], t[0]["name"], t[1]["name"], s["season"]))
    if gaps:
        b, c = max(gaps), min(gaps)
        out["margin"] = {"v": b[0], "name": b[1], "over": b[2], "season": b[3]}
        out["closest"] = {"v": c[0], "name": c[1], "over": c[2], "season": c[3]}
    climbs = []
    for prev, cur in zip(full, full[1:]):
        pr = {r["name"]: i + 1 for i, r in enumerate(sorted(prev["table"], key=lambda r: -r["total"]))}
        for i, r in enumerate(sorted(cur["table"], key=lambda r: -r["total"])):
            if r["name"] in pr:
                climbs.append((pr[r["name"]] - (i + 1), r["name"], pr[r["name"]], i + 1, cur["season"]))
    if climbs:
        c = max(climbs)
        if c[0] > 0:
            out["climb"] = {"v": c[0], "name": c[1], "from": c[2], "to": c[3], "season": c[4]}
    return out


# --------------------------------------------------------------------------- gate for the scheduler

def should_run():
    """True during a match window (any kickoff from 20 min before to 3 h after), otherwise when the
    live site's data is more than 50 minutes old. (GitHub often starts scheduled jobs 15-30 minutes
    late, so this goes by the age of the published data rather than the clock.)"""
    t = now()
    try:
        fixtures = fpl.main("fixtures/", max_age=6 * 3600)
    except Exception:
        return True
    for f in fixtures:
        ko = parse_time(f.get("kickoff_time"))
        if ko and ko - dt.timedelta(minutes=20) <= t <= ko + dt.timedelta(hours=3):
            return True
    site = os.environ.get("SITE_DATA_URL")
    if not site:
        return t.minute < 15
    try:
        req = urllib.request.Request(f"{site}?t={int(t.timestamp())}", headers={"User-Agent": fpl.UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            updated = parse_time(json.loads(r.read())["meta"]["updated"])
        return t - updated > dt.timedelta(minutes=50)
    except Exception:
        return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--rewrite", type=int, default=None)
    a = ap.parse_args()
    if a.gate and not a.force and not should_run():
        print("Outside a match window and the site was updated recently - skipping.")
        sys.exit(0)
    build(a)
