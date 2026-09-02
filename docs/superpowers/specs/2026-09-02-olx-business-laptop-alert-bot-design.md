# OLX Business Laptop Alert Bot — Design Spec

Date: 2026-09-02

## Purpose

Monitor OLX.ro for new laptop listings and email an alert when a
business-class laptop (ThinkPad / Latitude / EliteBook family) with
strong specs appears at a bargain price. Runs unattended, hourly, on
an always-on Windows mini PC (same box running Jellyfin).

## Scope

In scope:
- Scraping one OLX category/search URL (laptops, sorted by newest).
- Hard filtering on brand/model, RAM, CPU generation, storage type,
  price, and "defective/for parts" exclusion.
- A deal-quality score (% below a manual reference price per model).
- Deduplication so the same listing is never emailed twice.
- Email notification via Gmail SMTP.
- Scheduled execution via Windows Task Scheduler (hourly).

Out of scope (deferred, not building now):
- Multi-category / multi-site support (only OLX laptops).
- Learning market prices automatically from scraped history (may be
  a future iteration once the manual reference table proves useful).
- Web UI / dashboard. This is a headless script + email only.
- Parsing the listing detail page (title-only parsing for v1).

## Reference filter link

```
https://www.olx.ro/electronice-si-electrocasnice/laptop-calculator-gaming/laptopuri/?search%5Bfilter_float_price%3Ato%5D=1500&search%5Border%5D=created_at%3Adesc
```
(Price cap raised to 1500 lei here vs. the general link, because
business-class laptops meeting the spec bar rarely appear under 1000.)

## Architecture

```
Windows Task Scheduler (every 60 min)
      │
      ▼
scraper.py   → HTTP GET the filter URL above, parse listing cards from HTML
      │
      ▼
parser.py    → per listing: id, title, price, url, location, posted_at
      │
      ▼
filter.py    → hard filters (see below); listings that fail are dropped
      │
      ▼
scorer.py    → % below reference price, from a manual per-model table
      │
      ▼
db.sqlite    → skip if id already seen; otherwise record + pass through
      │
      ▼
notifier.py  → email via Gmail SMTP for each new passing listing
```

Each run is stateless except for `db.sqlite`, which persists the set
of listing IDs already processed. No long-running process — the
script starts, does one pass, exits.

## Hard filters (`filter.py`)

A listing must pass ALL of the following to proceed to scoring:

1. **Not defective/for parts.** Title (and short description, if
   available) does not contain: `defect`, `nefunctional`, `pe piese`,
   `pentru piese`, `pt piese`, `spart`, `crapat`, `nu porneste`
   (case-insensitive, diacritic-insensitive match).
2. **Business-class model.** Title matches one of the known model
   families (initial list, extend as needed):
   - Lenovo ThinkPad: `T4[0-9]0`, `T5[0-9]0`, `X13`, `X1`, `P14s`, `L14`
   - Dell Latitude: `Latitude \d{4}`
   - HP: `EliteBook \d{3}`, `ProBook \d{3}`
3. **RAM >= 16GB.** Extracted via regex `(\d+)\s*GB` (or `Gb`, `gb`) in
   the title. If no RAM is mentioned, the listing is EXCLUDED (can't
   confirm the requirement).
4. **CPU generation.** Intel: `i[3579]-1[1-3]\d{2}` (11th–13th gen) or
   explicit "gen 11/12/13" wording. AMD: `Ryzen [5-9] Pro (5|6|7)\d{3}`
   or better. If CPU model is not mentioned, the listing is EXCLUDED.
5. **Storage.** Excluded if the title explicitly contains `HDD`
   without also mentioning `SSD`. If storage is not mentioned at all,
   the listing is INCLUDED (business laptops in this class ship with
   SSD by default, but this is a known false-accept risk — see Risks).
6. **Price <= 1500 lei.**

Rules 1–6 are all AND'd together (a listing must pass every rule).

## Scoring (`scorer.py`)

For listings that pass all hard filters:

```
score_pct = (reference_price[model] - listing_price) / reference_price[model] * 100
```

`reference_price` is a manually maintained table in `config.yaml`,
one entry per model family, e.g.:

```yaml
reference_prices:
  "ThinkPad T480": 1800
  "ThinkPad T490": 2000
  "ThinkPad T14": 2200
  "ThinkPad X13": 2100
  "ThinkPad P14s": 2400
  "Latitude 5490": 1600
  "EliteBook 840": 1700
  # ... extend as needed
```

If a matched model has no reference price entry, the listing is still
emailed but the email states "scor indisponibil (adauga pret referinta
in config)" instead of a percentage. This surfaces gaps in the table
without silently dropping otherwise-qualifying listings.

## Deduplication (`db.sqlite`)

Single table:

```sql
CREATE TABLE seen_listings (
    id TEXT PRIMARY KEY,
    title TEXT,
    price INTEGER,
    score_pct REAL,
    seen_at TEXT
);
```

Before scoring, skip any listing whose `id` already exists in the
table. After a successful email send, insert the row.

## Notification (`notifier.py`)

- Gmail SMTP (`smtp.gmail.com:587`, STARTTLS) using an app password
  stored in `config.yaml` (local file, not committed to any repo).
- One email per new qualifying listing (simplicity over batching,
  volume expected to be low given the hard filters).
- Subject: `[OLX Deal] {model} — {price} lei ({score_pct}% sub referinta)`
- Body: title, price, score, location, posted date, direct link.

## Error handling

- Any scraping/parsing failure is logged to `bot.log` (rotating,
  keep last 14 days) with timestamp and exception detail. The run
  exits cleanly without emailing an error — avoids noise from
  transient site hiccups.
- If 3 consecutive scheduled runs fail (tracked via a small state
  file or the log), send a single "bot is down" email so it doesn't
  fail silently forever.
- Network timeouts: 15s request timeout, no retries within a run
  (next hourly run acts as the retry).

## Configuration (`config.yaml`)

```yaml
filter_url: "https://www.olx.ro/...&search[filter_float_price:to]=1500&..."
max_price: 1500
min_ram_gb: 16
excluded_keywords: ["defect", "nefunctional", "pe piese", ...]
business_models: ["ThinkPad T4", "ThinkPad T5", ...]
reference_prices: {...}
gmail:
  address: "..."
  app_password: "..."  # local only, never committed
  to: "..."
```

## Testing plan

1. Manual run of `scraper.py` against the live filter URL; confirm
   10–15 listings are extracted with correct id/title/price/link.
2. Unit tests for `filter.py` against a fixed set of sample titles
   covering: defective listing (excluded), non-business model
   (excluded), business model but 8GB RAM (excluded), business model
   but old CPU (excluded), HDD-only (excluded), a clean qualifying
   listing (included).
3. Unit test for `scorer.py`: known model + price → expected %.
4. End-to-end dry run with email sending mocked, verify DB dedup
   (second run with same data emits nothing).
5. One real end-to-end test sending an actual email to confirm SMTP
   credentials work.

## Deployment

- Python venv on the mini PC, project folder alongside (not inside)
  the Jellyfin install.
- `run.bat` activates the venv and runs `scraper.py`.
- Windows Task Scheduler: trigger hourly, action = `run.bat`, run
  whether user is logged on or not.

## Risks / open questions carried forward

- Title-only parsing will miss or misclassify listings with unusual
  phrasing (e.g., RAM mentioned only in the description, not title).
  Acceptable for v1; revisit if false-negative rate seems high.
- Storage-not-mentioned defaults to INCLUDED, which may let through
  the rare HDD-only business laptop that didn't say so. Acceptable
  trade-off vs. excluding legitimate SSD listings that just didn't
  spell it out.
- Reference price table needs periodic manual upkeep as market prices
  drift; no automatic recalibration in v1 (explicitly deferred).
