# Salmons FPL

Stats, awards and banter for the Salmons FPL Draft league (league 7963). The site is static (`site/`) and reads `site/data.json`, which `scripts/build.py` builds from the FPL Draft and main FPL APIs. GitHub Actions rebuilds and redeploys it to GitHub Pages: every 15 minutes during matches and hourly otherwise.

## Files you might edit

| File | What it's for |
|---|---|
| `config.json` | App name and subtitle, display names, nicknames, initials, chart colours, last season's champion (`last_season_champion_entry_id`) |
| `history.json` | Past seasons' champions and final tables (feeds Past seasons and All-time records) |
| `writeups/overrides.json` | Hand edits to any write-up line |
| `scripts/projections.py` | The projection formula and its knobs |

## Run it locally

```bash
python3 scripts/build.py
```

```bash
python3 -m http.server 8765 --directory site
```

Then open http://localhost:8765.

## How it works

- `scripts/fpl.py` caches API responses in `data/cache/`. Finished gameweeks are fetched once, and the rest is refetched each run.
- `scripts/build.py` works out every stat, then checks each manager's gameweek scores and the league totals against the API and prints any mismatches.
- `scripts/writeups.py` writes the copy once a gameweek's bonus points are confirmed. It uses Claude (`claude-sonnet-5-5`) if `ANTHROPIC_API_KEY` is set and template sentences otherwise. Each week is saved in `writeups/gwNN.json` and committed, so old weeks never change. Template weeks are upgraded to Claude copy the first time a key is available.
- `snapshots/gwNN.json` stores the table after each gameweek.

## One-off setup on GitHub

1. Create a new **public** repository (free Pages needs public), e.g. `salmons-fpl`. Don't add a README.
2. Push this folder:
   ```bash
   git remote add origin https://github.com/<you>/salmons-fpl.git
   ```
   ```bash
   git push -u origin main
   ```
3. Repo → **Settings → Pages** → Source: **GitHub Actions**.
4. Repo → **Settings → Secrets and variables → Actions** → **New repository secret**: name `ANTHROPIC_API_KEY`, value your key.
5. Repo → **Actions** tab → enable workflows if asked → **Update site** → **Run workflow**.

The site will then be live at `https://<you>.github.io/salmons-fpl/`.

## Force a refresh by hand

From the Actions tab: **Update site → Run workflow**. Or with the GitHub CLI:

```bash
gh workflow run update.yml
```

To regenerate one gameweek's write-ups (e.g. GW10):

```bash
gh workflow run update.yml -f rewrite=10
```

## Keeping it running

- **Update site** runs every 15 minutes, on off-peak minutes because GitHub delays jobs scheduled on the hour. It fully rebuilds during match windows, and otherwise whenever the published data is over 50 minutes old.
- **Watchdog** runs every 30 minutes and checks the live site. If the data is older than 40 minutes during a match, or 110 minutes otherwise, it re-triggers **Update site**. If the site has been stale for over 4 hours, the watchdog run fails and GitHub emails you.
- Each section of the build (write-ups, power, trades, Swap Shop, records, draft, waivers, live, preview) is isolated, so one crashing section is skipped and logged without blocking the rest.
- `scripts/check_data.py` checks `data.json` before every deploy. If it fails, the last good version of the site stays up.
- The app shows a "Scores may be behind" banner if the data is more than 45 minutes old during a match, or 3 hours otherwise.
- GitHub pauses scheduled workflows after 60 days without repo activity. Over the summer break, re-enable both workflows from the Actions tab before the new season.
