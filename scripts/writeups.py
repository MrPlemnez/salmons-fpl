"""Gameweek write-ups.

Once a gameweek is final (bonus confirmed), build.py hands this module a facts
JSON. If ANTHROPIC_API_KEY is set, Claude writes the copy; otherwise template
sentences are used. Each gameweek is stored in writeups/gwNN.json and never
regenerated, except template versions, which are upgraded to Claude copy the
first time a key is available (or with `build.py --rewrite N`).

Hand edits go in writeups/overrides.json, e.g.
    {"10": {"intro": "...", "motw": "...", "xi": {"123": "..."}}}
"""
import json
import os
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "writeups"
MODEL = "claude-sonnet-5-5"
KEYS = ["intro", "motw", "stinker", "bench", "bench_jam", "red_card", "gloves"]

# Bump STYLE whenever SYSTEM changes: every stored week is rewritten once in the new voice
# (unless it has hand edits in overrides.json, which always win).
STYLE = 2

SYSTEM = """You write the weekly column for a private FPL Draft league's stats site, read by a group of mates in a WhatsApp group who have known each other for years. The league is called Salmons and its crest is "Stoke Salmon FC".

Voice: classic British Premier League fantasy banter. Think the group chat after a terrible gameweek, crossed with a pundit who has seen it all and is unimpressed. Address the readers as "gentlemen". Mix bone-dry deadpan with proper football-banter energy:
- Lean on the game's shared language and clichés, used knowingly: "bottled it", "squeaky bum time", "can he do it on a cold, wet Tuesday night in Stoke?", "parked the bus", "Fergie time", "Sunday League", "the lads are buzzing", "absolute scenes", "differential", "set and forget", "played himself into form", "the bench is where points go to die", "a six-pointer", "the title race is ON", "never in doubt", "you can't buy that", "in his pocket", "hospital ball", "worldie", "rinsed".
- Roast the managers' decisions, not the managers as people: benching the haul, owning the player who got sent off, trading away the bloke who then scored twice, being top and then not.
- Find the league angle in every fact: whose player hurt whose, who profited from a player someone else dropped, who climbed, who fell, who is "having a mare".
- Punchlines land at the end of a sentence. Short sentences. One good joke beats three average ones. Vary the openings; don't start every award the same way.
- Example register: "Prime's keeper denied Pickle's defender. Good for Prime, awkward at the next dinner." / "Eight points on the bench and a 34 on the board. Somebody tell him the bench isn't a trophy cabinet."

Keep it affectionate: no slurs, nothing about anyone's real life, job, appearance, family or relationships, and nothing genuinely nasty. Don't put invented quotes in the mouths of real people (players, managers, pundits).

Hard rules:
- Use ONLY the facts in the JSON. Never invent goals, assists, minutes, scores, injuries, transfers or match events. If a detail isn't in the data, leave it out. The jokes can be made up; the facts can't.
- Refer to managers by the names given in the data.
- Premier League clubs by their usual short names (Spurs, Man City, Forest are fine).
- intro: 4-7 sentences: the notable real results, the top and bottom scores, movement at the top of the table.
- Each award: 2-5 sentences.
- xi: one entry per player in the team of the week, 1-3 sentences each, using the element id given.
- If an award is null in the data, return an empty string for it."""

SCHEMA = {
    "type": "object",
    "properties": {
        **{k: {"type": "string"} for k in KEYS},
        "xi": {"type": "array", "items": {
            "type": "object",
            "properties": {"element": {"type": "integer"}, "text": {"type": "string"}},
            "required": ["element", "text"], "additionalProperties": False}},
    },
    "required": KEYS + ["xi"],
    "additionalProperties": False,
}


def _path(gw):
    return DIR / f"gw{gw:02d}.json"


def overrides():
    f = DIR / "overrides.json"
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text())
    except json.JSONDecodeError:
        print("  ! writeups/overrides.json is not valid JSON - ignoring it")
        return {}


def apply_overrides(w, ov):
    out = dict(w)
    out["xi"] = dict(w.get("xi", {}))
    for k, v in ov.items():
        if k == "xi" and isinstance(v, dict):
            out["xi"].update({str(a): b for a, b in v.items()})
        elif k in KEYS:
            out[k] = v
    return out


def get(gw, facts, force=False):
    DIR.mkdir(exist_ok=True)
    f = _path(gw)
    have_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if f.exists() and not force:
        stored = json.loads(f.read_text())
        current = stored.get("style", 1) == STYLE
        if current and (stored.get("source") == "claude" or not have_key):
            return stored
        if stored.get("source") == "claude" and not have_key:
            return stored  # never downgrade Claude copy to templates
    w = None
    if have_key:
        w = _claude(gw, facts)
    if w is None:
        if f.exists() and not force and json.loads(f.read_text()).get("source") == "claude":
            return json.loads(f.read_text())  # API failed: keep the existing Claude copy
        w = _template(facts)
    w["style"] = STYLE
    f.write_text(json.dumps(w, indent=1, ensure_ascii=False))
    return w


def _claude(gw, facts):
    try:
        import anthropic
    except ImportError:
        print("  ! anthropic package not installed - using templates")
        return None
    try:
        client = anthropic.Anthropic()
        resp = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
            system=SYSTEM,
            messages=[{"role": "user", "content": "Gameweek facts:\n" + json.dumps(facts, ensure_ascii=False)}],
        )
        if resp.stop_reason != "end_turn":
            print(f"  ! GW{gw} write-up stopped with {resp.stop_reason} - using templates")
            return None
        text = next(b.text for b in resp.content if b.type == "text")
        data = json.loads(text)
        out = {k: data.get(k, "") for k in KEYS}
        out["xi"] = {str(x["element"]): x["text"] for x in data.get("xi", [])}
        out["source"] = "claude"
        print(f"  GW{gw} write-up generated by {resp.model}")
        return out
    except anthropic.APIStatusError as e:
        print(f"  ! GW{gw} write-up API error {e.status_code} - using templates")
    except anthropic.APIConnectionError:
        print(f"  ! GW{gw} write-up: could not reach the API - using templates")
    except (StopIteration, json.JSONDecodeError, KeyError) as e:
        print(f"  ! GW{gw} write-up unreadable ({e}) - using templates")
    return None


# --------------------------------------------------------------------------- templates

def _names(xs):
    xs = list(xs)
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def _stat_bits(p):
    s = p.get("stats", {})
    bits = []
    if s.get("goals_scored"):
        bits.append(f"{s['goals_scored']} goal{'s' if s['goals_scored'] > 1 else ''}")
    if s.get("assists"):
        bits.append(f"{s['assists']} assist{'s' if s['assists'] > 1 else ''}")
    if s.get("clean_sheets") and p["pos"] in ("GK", "DEF"):
        bits.append("a clean sheet")
    if s.get("saves") and p["pos"] == "GK":
        bits.append(f"{s['saves']} saves")
    if s.get("bonus"):
        bits.append(f"{s['bonus']} bonus")
    if s.get("defensive_contribution", 0) >= 10 and p["pos"] != "GK":
        bits.append(f"{s['defensive_contribution']} defensive actions")
    return bits


def _template(facts):
    """Fallback copy when there's no API key. Facts are slotted into banter lines; the line
    choice is seeded by gameweek so a week always reads the same."""
    rnd = random.Random(facts["gameweek"])
    pick = rnd.choice
    a = facts["awards"]
    table = facts["league_table_after"]
    g = facts["gameweek"]
    top = table[0]
    second = table[1] if len(table) > 1 else None
    res = facts["premier_league_results"]
    motw, stink = a["manager_of_the_week"], a["stinker_of_the_week"]

    intro = [pick([f"Good evening, gentlemen. Gameweek {g} is in the books.",
                   f"Gentlemen. Gameweek {g}. Let's get into it.",
                   f"Evening, gentlemen. Gameweek {g} has been and gone, and it's left a mark."])]
    if res:
        intro.append("On the pitch: " + _names(res[: min(3, len(res))]) + ".")
    intro.append(pick([
        f"{_names(motw['managers'])} led the way with {motw['points']}, while {_names(stink['managers'])} limped in on {stink['points']}.",
        f"{_names(motw['managers'])} had the lads buzzing with {motw['points']}. {_names(stink['managers'])} posted {stink['points']} and has gone quiet in the chat.",
        f"Top score {motw['points']} for {_names(motw['managers'])}. Bottom score {stink['points']} for {_names(stink['managers'])}. Absolute scenes at both ends.",
    ]))
    if second:
        gap = top["total"] - second["total"]
        if gap == 0:
            intro.append(f"{top['manager']} and {second['manager']} are level on {top['total']}. The title race is ON.")
        elif gap <= 10:
            intro.append(f"{top['manager']} leads on {top['total']}, just {gap} clear of {second['manager']}. Squeaky bum time, and it's only gameweek {g}.")
        else:
            intro.append(pick([f"{top['manager']} sits top on {top['total']}, {gap} clear of {second['manager']}, and is starting to look like he's parked the bus.",
                               f"{top['manager']} leads by {gap} over {second['manager']}. Somebody needs to put a shift in."]))
    climbers = [r for r in table if r["moved"] > 0]
    if climbers:
        c = max(climbers, key=lambda r: r["moved"])
        intro.append(f"{c['manager']} climbs {c['moved']} to {_ordinal(c['rank'])}, playing himself into form.")
    intro.append(pick(["As you were.", "Nobody panic.", "Onwards.", "See you in the group chat."]))

    def sheet(name):
        return facts["team_sheets"].get(name, {})

    m0 = motw["managers"][0]
    best = sheet(m0).get("scorers", [])[:3]
    motw_t = pick([f"{motw['points']} points. Never in doubt.",
                   f"{_names(motw['managers'])} with {motw['points']}, the best of the week. You can't buy that.",
                   f"{motw['points']} on the board. Take a bow, {m0}."])
    if best:
        motw_t += " " + _names([f"{p['name']} ({p['points']})" for p in best]) + " did the damage."
    mrow = next((r for r in table if r["manager"] == m0), None)
    if mrow:
        motw_t += f" Up to {_ordinal(mrow['rank'])} on {mrow['total']}." if mrow["moved"] > 0 else f" Sits {_ordinal(mrow['rank'])} on {mrow['total']}."

    s0 = stink["managers"][0]
    srow = next((r for r in table if r["manager"] == s0), None)
    stink_t = pick([f"{stink['points']} points. Sunday League stuff.",
                    f"{stink['points']} points. The lowest of the week, and it wasn't close to being a differential.",
                    f"{stink['points']}. Bottled it."])
    sbest = sheet(s0).get("scorers", [])[:1]
    if sbest:
        stink_t += f" {sbest[0]['name']} was his top scorer with {sbest[0]['points']}, which tells you everything about the rest."
    if srow and srow["moved"] < 0:
        stink_t += f" Down {-srow['moved']} to {_ordinal(srow['rank'])}. Having a mare."

    b = a["bench_of_the_week"]
    bench_t = ""
    if b["managers"]:
        left = sheet(b["managers"][0]).get("bench_left", [])
        hits = [p for p in left if p["points"] > 0]
        bench_t = f"{b['points_left_on_bench']} points left on the bench."
        if hits:
            bench_t += " " + _names([f"{p['name']} ({p['points']})" for p in hits]) + " watched it all in a bib."
        bench_t += " " + pick(["The bench is where points go to die.",
                               "The bench isn't a trophy cabinet, gentlemen.",
                               "Set and forget. Mostly forget."])

    j = a["bench_jam_of_the_week"]
    jam_t = ""
    if j:
        jam_t = (f"{j['came_on_for']} didn't play, so {j['player']['name']} came off {j['manager']}'s bench "
                 f"and scored {j['player']['points']}.")
        bits = _stat_bits(j["player"])
        if bits:
            jam_t += " " + _names(bits).capitalize() + "."
        jam_t += " " + pick(["Luck is a skill if you say it confidently.",
                             "Fergie-time management.",
                             "Tactical genius, or he forgot to make changes. You decide."])

    r = a["red_card_of_the_week"]
    red_t = ""
    if r:
        st = r["player"]["stats"]
        why = "a red card" if st.get("red_cards") else ("an own goal" if st.get("own_goals") else
                                                         ("a missed penalty" if st.get("penalties_missed") else None))
        red_t = f"{r['player']['name']} ({r['player']['club']}) returned {r['player']['points']} for {r['manager']}."
        if why:
            red_t += f" Featuring {why}."
        red_t += " " + pick(["Hospital ball, but for points.", "Thanks for coming.", "One for the blooper reel."])

    gl = a["gloves_of_the_week"]
    gl_t = ""
    if gl:
        st = gl["player"]["stats"]
        gl_t = f"{gl['player']['name']} ({gl['player']['club']}) returned {gl['player']['points']} for {gl['manager']}."
        if st.get("goals_conceded"):
            gl_t += f" Conceded {st['goals_conceded']}."
        if st.get("saves"):
            gl_t += f" Made {st['saves']} saves, for what it's worth."
        gl_t += " " + pick(["Gloves made of butter.", "A keeper in name only.", "Could he do it on a cold, wet Tuesday night in Stoke? No."])

    xi = {}
    for p in facts["team_of_the_week"]["players"]:
        bits = _stat_bits(p)
        t = f"{p['points']} points for {p['owner']}"
        t += (": " + _names(bits) + "." if bits else ".")
        if p["points"] >= 13:
            t += " " + pick(["Worldie of a week.", "Rinsed them.", "Absolute scenes."])
        xi[str(p["element"])] = t

    return {"intro": " ".join(intro), "motw": motw_t, "stinker": stink_t, "bench": bench_t,
            "bench_jam": jam_t, "red_card": red_t, "gloves": gl_t, "xi": xi, "source": "template"}


def _ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"
