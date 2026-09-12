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
- Multi-site support (OLX only). Multi-category IS in scope for the
  SSD-deal rule (see below) — it scans laptops + desktop/mini-PC
  categories — but the main business-laptop rule stays laptops-only.
- Learning market prices automatically from scraped history (may be
  a future iteration once the manual reference table proves useful).
- Web UI / dashboard. This is a headless script + email only.
- Fetching the listing detail page (search-results page data is
  sufficient — see Data source below).

## Data source (important technical finding)

OLX's search-results page does NOT render full listing cards into
static server HTML — only 3 "promoted" cards are present as real DOM
elements; the rest are hydrated client-side from a JSON blob embedded
in the page: a `<script>` sets
`window.__PRERENDERED_STATE__ = "<JSON-escaped JSON string>";`.

This blob is far better than scraping rendered HTML: it contains, per
ad, `id`, `title`, `description` (full text, not just title), `url`,
`createdTime`, `location.pathName`, `price.regularPrice.value`, and a
`params` array of structured filters the seller picked, e.g.:

```json
{
  "state": "Utilizat" | "Nou",
  "tip_stocare": "SSD" | "HDD" | "HDD+SSD",
  "capacitate_memorie_ram": "< 4 GB" | "4 - 6 GB" | "6 - 8 GB" |
                            "8 - 12 GB" | "12 - 16 GB" | "> 16 GB",
  "producator_procesor": "Intel " | "AMD " | "Apple",
  "tip_placa_video": "Integrata" | "Dedicata",
  "diagonala": "..."
}
```

There is no structured CPU-generation field — that still requires a
regex over `title` + `description`. RAM is bucketed, not exact — see
filter rule 3 below for how the buckets are handled.

**Extraction:** regex out the JSON string assigned to
`window.__PRERENDERED_STATE__` from the raw HTML, `json.loads` it
twice (it's a JSON string containing a JSON string), then read
`state["listing"]["listing"]["ads"]` — a list of ad objects as above.
No BeautifulSoup / CSS selectors needed; no JS execution needed. A
single `requests.get()` on the filter URL is sufficient.

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
scraper.py   → HTTP GET the filter URL above (one request, one page)
      │
      ▼
parser.py    → extract window.__PRERENDERED_STATE__ JSON, return list of
               ad dicts: id, title, description, price, url, location,
               created_time, params (see Data source below)
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

All text matching (rules 1, 2, 4) runs against the **title only**
(lowercased, diacritic-stripped: ă/â/î/ș/ş/ț/ţ → a/a/i/s/s/t/t) — not
the description. Live testing found that reseller descriptions are
full of boilerplate (trade-in/buyback disclaimers, accessory lists,
other-model mentions, paid upgrade offers) that causes false matches
in both directions when included.

1. **Not defective/for parts.** Does not contain: `defect`,
   `nefunctional`, `pe piese`, `pentru piese`, `pt piese`, `spart`,
   `crapat`, `nu porneste`.
2. **Business-class model.** Matches one of the known model families
   (initial list, extend as needed):
   - Lenovo ThinkPad: `t4[0-9]0`, `t5[0-9]0`, `x13`, `x1`, `p14s`, `l14`
   - Dell Latitude: `latitude ?\d{4}`
   - HP: `elitebook ?\d{3}`, `probook ?\d{3}`
3. **RAM >= 16GB.** Uses the `capacitate_memorie_ram` param first:
   - `"> 16 GB"` → pass
   - `"12 - 16 GB"` → ambiguous (covers 12–16); fall back to a regex
     `(\d+)\s*gb` over title+description looking for an explicit
     `16gb`/`16 gb` mention. Pass only if found; otherwise EXCLUDE.
   - Any lower bucket, or the param missing entirely → EXCLUDE.
4. **CPU generation.** No structured field exists for this — regex
   only. Intel: `i[3579]-1[1-3]\d{2}` (11th–13th gen model numbers) or
   explicit `gen(eratia)? 1[1-3]` wording. AMD: `ryzen [5-9] pro ?(5|6|7)\d{3}`
   or newer. If no match, EXCLUDE.
5. **Storage.** Uses the `tip_stocare` param: `"SSD"` or `"HDD+SSD"` →
   pass. `"HDD"` alone → EXCLUDE. Param missing → EXCLUDE (structured
   data is available for essentially every listing on this category,
   so "missing" almost always means the ad predates the field and is
   old/stale).
6. **Price <= 1500 lei.** From `price.regularPrice.value`. Ads with no
   regular price (`free`/`exchange` only) are EXCLUDED.
7. **Private seller only.** Uses the ad's structured `isBusiness` field
   directly (not a text heuristic — OLX marks shop/dealer listings
   explicitly). `isBusiness: true` → EXCLUDE. Motivation: the user
   wants "super ocazii" from private sellers, not dealer stock at
   dealer margins.

Rules 1–7 are all AND'd together (a listing must pass every rule).

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

The two alert rules (business-laptop deals and the SSD-deal rule below)
share this one table but namespace their keys (`biz:<id>` vs `ssd:<id>`)
so the same ad ID can independently qualify — and get deduplicated —
under both rules without colliding.

## Second rule: SSD-deal alert (`passes_ssd_deal_filter`, any specs)

A second, independent alert rule, added after the first version shipped:
ignore CPU/RAM/model entirely and alert on ANY listing (laptop, desktop,
mini PC, or a bare drive sold as a component) with a real SSD of at
least a minimum capacity, at a throwaway price — on the theory that
some sellers don't realize how much their SSD alone is currently worth
and underprice the whole system (or the drive itself).

Scans three categories: `laptopuri`, `sisteme-pc-si-gaming`
(desktops/mini-PCs land here on OLX), and
`componente-laptop-pc/hard-disk-uri` (bare SSD/HDD drives sold as
components, not inside a system — added after the user asked whether
standalone drives were covered; they weren't, until this category was
added). That third category uses a DIFFERENT params schema than the
other two: `tip` (`"SSD"`/`"HDD"`) instead of `tip_stocare`, since a
bare drive can't be "half SSD, half HDD" — `filters.is_ssd()` checks
both schemas.

Rules (all AND'd):
1. Private seller only (`is_business` false) — same as the main rule.
2. Is an SSD: `tip_stocare` param is `"SSD"` or `"HDD+SSD"` (system
   listings), OR `tip` param is `"SSD"` (standalone-drive listings) —
   not `"HDD"` alone in either schema.
3. SSD capacity >= `min_ssd_gb` (default 512GB), extracted from
   `title + " " + description` by taking the largest GB/TB number
   mentioned — no structured capacity field is used since the
   standalone-drive category's `capacitate` param is bucketed
   (`"< 1 TB"`, `"1 - 2 TB"`, etc.) and too coarse. Doesn't require the
   number to sit next to the word "ssd": real titles often put a model
   number in between (e.g. "SSD Kingston A400, 960GB"), which broke an
   earlier, stricter version of this regex. Unlike the main rule, this
   one DOES read the description: false-positive risk is accepted here
   because the rule itself is explicitly a loose "any specs" scan, not
   the precision-focused business-laptop rule.
4. Price threshold, which DIFFERS by listing type:
   - Laptop/PC-system listings: flat `max_price` (default 800 lei) — a
     bundled system's price isn't a proxy for the drive's own value, so
     this stays a fixed ceiling regardless of capacity.
   - Standalone-drive listings: NOT the flat `max_price`, and NOT a fixed
     capacity→price tier table either (an earlier version used one —
     `{512: 150, 1000: 200, 2000: 300}` — but real market prices move
     and hand-picked tiers meant genuinely cheap 2TB+ drives almost never
     qualified, since 300 lei was already unrealistically low for a real
     2TB SSD). Replaced with a LIVE market median: every standalone-drive
     price the bot observes (any listing that's an SSD, private seller,
     not a part-out listing, valid capacity) gets recorded once per ad
     into `ssd_price_observations` (`db.record_price_observation`),
     keyed by `filters.capacity_bucket(capacity_gb)` — capacities are
     snapped to the nearest of `[128, 256, 512, 1000, 2000, 4000, 8000]`
     GB so "500GB" and "512GB" sellers pool into the same bucket. Before
     alerting, `filters.passes_ssd_deal_filter` looks up
     `db.get_price_stats(conn, bucket)` → `(median, count)`; requires
     `count >= ssd_deal.min_samples` (default 5 — a median from 1-2 ads
     is noise, not a market rate) and alerts only if
     `price <= median * ssd_deal.discount_threshold` (default 0.5, i.e.
     50%+ off the observed market rate for that exact capacity). This
     self-calibrates over time and treats every capacity the same way —
     2TB, 3TB, 4TB+ drives get real deals recognized once enough samples
     exist, instead of being capped by a guessed number nobody updates.
     Price recording happens in `main.py` for every standalone-drive
     listing scanned (whether or not it ends up alerting), independent
     of whether the ad has already been seen for alert-dedup purposes —
     `INSERT OR IGNORE` on the ad id keeps a repeatedly-rescanned ad from
     being double-counted into the median.

No scoring step — "cheap enough" is binary here (price threshold), not a %
below a reference. Notification uses a distinct email subject
(`[OLX SSD Deal]`) so it's visually distinct from `[OLX Deal]` business
alerts in the inbox.

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
   40+ listings are extracted with correct id/title/price/link/params.
2. Unit tests for `filter.py` against a fixed set of sample ad dicts
   (built from real captured param shapes) covering: defective listing
   (excluded), non-business model (excluded), business model but RAM
   bucket "8 - 12 GB" (excluded), business model but no CPU-gen match
   (excluded), `tip_stocare: "HDD"` (excluded), a clean qualifying
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

- CPU generation has no structured field and relies entirely on regex
  over free-text title+description; unusual phrasing will cause a
  false-negative exclusion. Acceptable for v1; revisit if too many
  otherwise-good listings get excluded for missing a CPU match.
- The RAM bucket `"12 - 16 GB"` requires an explicit "16GB" text
  mention to pass; a seller who only picked the dropdown bucket
  without typing RAM anywhere in the text will be excluded even at
  exactly 16GB. Accepted false-negative risk, same reasoning as CPU.
- `window.__PRERENDERED_STATE__` is an internal implementation detail
  of OLX's frontend and could change format or be removed in a
  redesign. If scraping starts failing, this is the first thing to
  re-verify (re-run the extraction Task 2's script against a fresh
  page fetch).
- Reference price table needs periodic manual upkeep as market prices
  drift; no automatic recalibration in v1 (explicitly deferred).
