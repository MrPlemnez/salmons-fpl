"""Projected points per gameweek. One module, all knobs at the top. Used by
Power, Preview, Waiver wire, Trades and Swap Shop.

For each player and each of the next N gameweeks:

    proj = per_game * fixture_factor * minutes_factor * availability

per_game
    FPL's own `ep_next` (main game) divided by the fixture factor of his next
    gameweek, so that it becomes a fixture-neutral "points per match" figure.
    If he isn't available right now (ep_next is 0 or missing), fall back to his
    season points-per-game x PPG_FALLBACK so a returning player still projects
    something for later weeks.

fixture_factor
    Sum of FDR_FACTOR[difficulty] over his fixtures that gameweek (0 for a blank,
    roughly double for a double gameweek).

minutes_factor
    MIN_FLOOR + (1 - MIN_FLOOR) * reliability, where reliability is his average
    minutes over the last 5 gameweeks divided by FULL_MINUTES (capped at 1).

availability
    Week 1: chance_of_playing_next_round / 100 (100 if no flag, 0 if he has left
    the league). Later weeks recover by RECOVERY per week (flags are usually
    short-term), except players who have left, who stay at 0.
"""

FDR_FACTOR = {1: 1.20, 2: 1.10, 3: 1.00, 4: 0.88, 5: 0.76}
MIN_FLOOR = 0.5
FULL_MINUTES = 75.0
PPG_FALLBACK = 0.9
RECOVERY = 0.4
WEEKS = 3


def _fixture_factor(fixtures):
    return sum(FDR_FACTOR.get(f["fdr"], 1.0) for f in fixtures)


def project(player, team_fixtures, gws, recent_minutes):
    """player: dict with ep_next, ppg, status, cop.
    team_fixtures: {gw: [ {fdr: int, ...}, ... ]} for the player's club.
    gws: list of upcoming gameweek numbers.
    recent_minutes: list of minutes in his last (up to) 5 gameweeks.
    Returns a list of projections, one per gw."""
    if not gws:
        return []
    status = player.get("status") or "a"
    if status in ("u", "n"):
        return [0.0 for _ in gws]

    first = team_fixtures.get(gws[0], [])
    ff1 = _fixture_factor(first)
    ep = player.get("ep_next")
    if ep and ep > 0 and ff1 > 0:
        per_game = ep / ff1
    else:
        per_game = (player.get("ppg") or 0.0) * PPG_FALLBACK

    rel = 0.0
    if recent_minutes:
        rel = min(1.0, (sum(recent_minutes) / len(recent_minutes)) / FULL_MINUTES)
    minutes_factor = MIN_FLOOR + (1 - MIN_FLOOR) * rel

    cop = player.get("cop")
    if cop is None:
        avail1 = 1.0 if status in ("a", "d") else 0.0
        if status == "d":
            avail1 = 0.75
    else:
        avail1 = cop / 100.0

    out = []
    for i, gw in enumerate(gws):
        avail = min(1.0, avail1 + RECOVERY * i) if avail1 < 1 else 1.0
        ff = _fixture_factor(team_fixtures.get(gw, []))
        out.append(round(per_game * ff * minutes_factor * avail, 2))
    return out
