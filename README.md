# OLX Business Laptop Alert Bot

Hourly scans OLX for ThinkPad/Latitude/EliteBook laptops with 16GB+
RAM, 11th-gen+ CPU, SSD, under 1500 lei, and emails a deal-quality
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
3. Copy `config.example.yaml` to `config.yaml` and fill in:
   - `gmail.address` / `gmail.to`: your Gmail address.
   - `gmail.app_password`: a Gmail **app password**, not your normal
     password. Generate one at https://myaccount.google.com/apppasswords
     (requires 2-Step Verification enabled on the account).
   - `reference_prices`: extend/adjust as you learn real market prices.
4. Run once manually to confirm it works:
   ```
   python -m olx_bot.main
   ```
   Check `bot.log` for errors, and confirm `seen_listings.db` was created.

## Running tests

```
python -m pytest -v
```

## Scheduling (Windows Task Scheduler)

1. Open Task Scheduler → Create Task.
2. General tab: name it "OLX Laptop Bot", select "Run whether user is
   logged on or not".
3. Triggers tab: New → Daily, recur every 1 day, then check "Repeat
   task every: 1 hour" for a duration of "Indefinitely".
4. Actions tab: New → Action "Start a program" → Program/script:
   full path to `run.bat` in this project folder.
5. Conditions/Settings tabs: uncheck "Start the task only if the
   computer is on AC power" if this is a laptop; leave defaults
   otherwise.
6. Save, then right-click the task → Run, to confirm it works end to
   end (check for a test email and a new `bot.log` entry).

## Troubleshooting

- No emails ever arriving: check `bot.log` first. If it shows
  `window.__PRERENDERED_STATE__ not found`, OLX likely changed their
  page structure — re-run the extraction logic manually against a
  fresh page fetch to see what changed.
- Gmail login failing: confirm you're using an app password, not your
  regular Gmail password, and that 2-Step Verification is on.
