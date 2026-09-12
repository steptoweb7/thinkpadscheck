# OLX Business Laptop Alert Bot

Hourly scans OLX for ThinkPad/Latitude/EliteBook laptops with 16GB+
RAM, 11th-gen+ CPU, SSD, under 1800 lei, and emails a deal-quality
score for each new match. Design: see
`docs/superpowers/specs/2026-09-02-olx-business-laptop-alert-bot-design.md`.

## Setup

1. Install Python 3.11+.
2. Create a virtual environment and install dependencies:
   ```
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Copy `config.example.yaml` to `config.yaml` and fill in your Gmail
   credentials:
   - `gmail.address` / `gmail.to`: your Gmail address.
   - `gmail.app_password`: a Gmail **app password**, not your normal
     password. Generate one at https://myaccount.google.com/apppasswords
     (requires 2-Step Verification enabled on the account).

   Everything else (price caps, models, SSD thresholds, `reference_prices`,
   etc.) lives in `settings.yaml`, which IS tracked in git — see
   "Changing settings" below. `config.yaml` should only ever contain the
   `gmail:` block; it stays out of git specifically so this file (and
   the password in it) never gets committed or pushed anywhere.
4. Run once manually to confirm it works:
   ```
   python -m olx_bot.main
   ```
   Check `bot.log` for errors, and confirm `seen_listings.db` was created.

## Changing settings (`settings.yaml`)

`settings.yaml` at the project root holds every non-secret setting:
`filter_url`, `max_price`, `reference_prices`, the whole `ssd_deal`
block. It's tracked in git, so changing a value, committing, and
pushing is enough — the deployment machine picks it up on its next
`git pull`, no manual edit on that machine required. `config.yaml`
(gitignored) only needs the `gmail:` block; if it also defines a key
that's in `settings.yaml`, the `config.yaml` value wins (for a one-off
local override without touching git), but this shouldn't normally be
needed.

## Standalone SSD/HDD deals use a self-learning market price

For bare-drive listings (the `componente-laptop-pc/hard-disk-uri`
category), the bot doesn't use a fixed price per capacity — it builds
its own market median over time from every standalone-drive price it
sees, grouped by capacity (512GB, 1TB, 2TB, etc.), and only alerts when
a price is `ssd_deal.discount_threshold` (default 0.6 = 40%+ off) below
that median. This means: **a fresh install won't alert on any capacity
until it has seen at least `ssd_deal.min_samples` (default 5) real
prices for that exact size** — give it a few days to build up history.
Once it has, this covers any capacity automatically (512GB, 1TB, 2TB,
4TB+), unlike the old fixed price table which had to be hand-tuned per
size and went stale.

## Alert history (`alerts_log.csv`)

Every alert actually emailed (both rules) also gets appended as a row to
`alerts_log.csv` in the project root — a plain, append-only CSV you can
open in Excel/Notepad/whatever, independent of the SQLite dedup DB.
Columns: `timestamp, rule, listing_id, title, price_lei, model,
score_pct, ssd_capacity_gb, location, posted_at, url`. `rule` is either
`business` or `ssd_deal`; whichever fields don't apply to that rule
(e.g. `model`/`score_pct` for an `ssd_deal` row) are left blank. Never
overwritten, never rewritten — only grows one row per new alert, so it
doubles as a full historical log of every deal the bot ever caught.

## Running tests

```
python -m pytest -v
```

## Scheduling (Windows Task Scheduler)

1. Open Task Scheduler → Create Task.
2. General tab: name it "OLX Laptop Bot", select "Run whether user is
   logged on or not".
3. Triggers tab: New → Daily, recur every 1 day, then check "Repeat
   task every: 1 hour" **for a duration of: "1 day"** (NOT
   "Indefinitely" — real-world testing found "Indefinitely" can
   silently stop re-firing after the first run on some Windows
   installs; "1 day" duration self-renews every day via the Daily
   trigger and has proven reliable).
4. Actions tab: New → Action "Start a program" → Program/script:
   full path to `run.bat` in this project folder, quoted if the path
   contains spaces (e.g. `"C:\OLX Scrape\run.bat"`). Also set
   "Start in" to the project folder.
5. Conditions tab: **uncheck "Start the task only if the computer is
   on AC power"** (and its sub-checkbox) — this is checked by default
   and, on at least one real desktop mini PC, silently prevented every
   automatic hourly run while manual "Run" still worked fine (manual
   runs ignore Conditions entirely, which is what made this
   confusing). Uncheck it even on a desktop, not just a laptop.
6. Save, then right-click the task → Run, to confirm it works end to
   end (check for a test email and a new `bot.log` entry). Then wait
   for at least one real automatic (non-manual) run and confirm
   `bot.log` gets a new entry on its own — a working manual Run does
   NOT prove the automatic schedule works (see Conditions above).

## Troubleshooting

- No emails ever arriving: check `bot.log` first. If it shows
  `window.__PRERENDERED_STATE__ not found`, OLX likely changed their
  page structure — re-run the extraction logic manually against a
  fresh page fetch to see what changed.
- Gmail login failing: confirm you're using an app password, not your
  regular Gmail password, and that 2-Step Verification is on.
