# Salmons FPL: build plan

Status: waiting for approval. Built from the 24 Hammy screenshots and a live check of league 7963 (19 Nov 2026, after GW10).

## What the API check found
- All Draft endpoints respond without sign-in. The main FPL `bootstrap-static` responds too.
- Current GW 10 is finished. GW11 is next, and waivers haven't processed yet.
- Standings after GW10: Ben 526, Jonny 466, Asher 443, Nicholas 442, Josh 427, Jack 418, Louie 414, Jamie 385. These get checked against the FPL site in step 2.
- Draft: 120 picks (8 × 15), held 17 Aug 2026.
- Transactions: 300 in total, 135 of them accepted.
- Trades: 2 so far, both state `p`. I'll confirm `p` means processed.
- `entry/{id}/history` always returns `points_on_bench: 0`. Bench points have to come from picks plus live points.
- No previous seasons are reachable. The league has no link back to an older league ID, so past seasons come from you (`history.json`).

## Architecture
- `scripts/fetch.py` caches raw API data under `data/raw/` and only re-fetches finished GWs once.
- `scripts/build.py` turns that into `site/data.json`, plus `site/gw/{n}.json` per gameweek and `snapshots/`.
- `scripts/projections.py` is the one documented projection module: `ep_next` adjusted for FDR, mins/90 over the last 5 games and chance of playing.
- `scripts/writeups.py` builds a facts JSON. If `ANTHROPIC_API_KEY` is set it calls `claude-sonnet-5-5`, otherwise it uses templates. Output goes to `writeups/gw{n}.json`, and `writeups/overrides.json` lets you edit any line.
- `site/` is a static HTML/CSS/JS app (no framework), with a PWA manifest and service worker.
- `.github/workflows/update.yml` runs every 15 min in match windows and hourly otherwise, then commits and deploys to Pages.

## Screen → data → calculation

| Screen | Data | Calculation |
|---|---|---|
| Home | details, history | leader + gap to 2nd; MOTW/Stinker = max/min `event_total`; climber/faller = `last_rank − rank`; deadline from bootstrap events |
| TOTW | picks + live per GW, PL fixtures | GW dropdown; awards: MOTW, Stinker, Bench (sum of non-subbed bench pts), Bench Jam (top auto-sub), Red Card (most negative owned starter), Gloves (worst owned GK that played); XI = best valid formation (1 GK, 3–5 DEF, 2–5 MID, 1–3 FWD) from owned players' GW pts; season-awards counts across all GWs |
| Midweek | `/event/{gw}/live`, picks | provisional live totals with auto-sub simulation, live bonus (BPS), cards; LIVE badge |
| Preview | projections, fixtures, injury news | best projected XI per manager, projected score, key fixtures, doubts (`chance_of_playing < 75`) |
| Waivers | transactions | latest round: claims (accepted/denied), drops, waiver order (`waiver_pick`) |
| Standings | details | rank, ▲▼ vs `last_rank`, GW pts, total, gap; 🏆 (c) from config |
| Power | projections, element-status | best projected XI avg over next 3 GWs; "N above/below table"; top 2 players, absentees, last-3 avg vs league avg |
| The race | history | cumulative lines, tap to highlight; GW grid with top (green) / bottom (red) |
| Squads | element-status, element-summary, fixtures | best XI by season pts, bench after dashed line; next 3 FDR chips; per-GW sparkbars; dead slots; best-XI/squad/bench pts, unavailable count |
| Needs | starters' GW points by position | stacked GK/DEF/MID/FWD %; fit-and-playing / held per position, shaded green/amber/red |
| Waiver wire | unowned players, projections, live DC stats | PROJ/WK, PTS, DEFCON/90 (green if ≥10 DEF / ≥12 MID in most games), next fixture; position + min-minutes filters |
| Trades | trades, transactions | follow each traded squad slot through later waiver swaps; pts since + 3-GW projection; win at ≥3 margin; won/lost/net table |
| Swap Shop | Needs + projections | pairs where A's surplus fills B's gap and vice versa, and both sides gain projected pts |
| Records (season) | history, picks + live, trades, transactions | high/low GW, biggest margin over 2nd, most bench pts, most trades, most transfers; Biggest hauls; Bench disasters |
| Records (all time) | `history.json` + this season once final | highest/lowest total, biggest title margin, closest race, biggest climb; near-final seasons excluded |
| Past seasons | `history.json` | gold card per season, tap to see final table, titles intro line |
| Draft 26/27 | choices, bootstrap, ownership timeline | 15 × 8 snake board; green/red by ±40 rank vs pick no.; faded if gone; Best value / Early misses with "for him" pts |

## Decisions
- Managers use first names, with Brahmes for Well done Sons cryin (`config.json`).
- Avada Kedavra is dropped, so Squads has two sub-tabs: Squads · Needs.
- The subtitle stays "(Retard League)".

## Design
White/black/yellow (#FFC800) per the brief, condensed display headings, tabular mono numbers, skeletons, count-ups, swipeable sub-tabs, pull to refresh, sticky table headers, tappable chart tooltips, "Me" toggle, share-image export (canvas → PNG) for award cards, dark mode.

## Build order
1. Fetcher + `data.json`, then check standings and GW10 against the FPL site and show you.
2. Tabs in nav order: This week → Table → Squads → Transfers → History.
3. Workflow + Pages deploy, then the setup walkthrough.
