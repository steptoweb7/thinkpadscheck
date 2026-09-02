# OLX Business Laptop Alert Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python script that hourly-scrapes OLX for business-class
laptops (ThinkPad/Latitude/EliteBook, 16GB+ RAM, 11th-gen+ CPU, SSD) under
1500 lei, and emails an alert with a deal-quality score for each new match.

**Architecture:** A single-pass script (`python -m olx_bot.main`) run by
Windows Task Scheduler every hour: `scraper` fetches the OLX search page →
`parser` extracts the embedded `window.__PRERENDERED_STATE__` JSON →
`filters` drops anything that isn't a qualifying business laptop →
`scorer` computes a % against a manual reference-price table → `db`
(SQLite) deduplicates against previously-seen listing IDs → `notifier`
emails each new qualifying listing via Gmail SMTP.

**Tech Stack:** Python 3.11+, `requests`, `PyYAML`, stdlib `sqlite3` /
`smtplib` / `re` / `json`, `pytest` for tests.

**Spec:** [docs/superpowers/specs/2026-09-02-olx-business-laptop-alert-bot-design.md](../specs/2026-09-02-olx-business-laptop-alert-bot-design.md)

## Global Constraints

- Price cap: 1500 lei (`price.regularPrice.value` from the parsed ad).
- RAM: >= 16GB, read from the `capacitate_memorie_ram` param (see spec
  rule 3 for the bucket/fallback logic — the `"12 - 16 GB"` bucket needs
  an explicit "16gb" text mention to pass).
- CPU: Intel 11th–13th gen (`i[3579]-1[1-3]\d{2}` or "gen 11/12/13"
  wording) or AMD Ryzen 5-9 PRO 5000-series+, matched via regex over
  `title + " " + description` (no structured field exists for this).
- Storage: `tip_stocare` param must be `"SSD"` or `"HDD+SSD"`.
- Business models (regex, word-bounded, case/diacritic-insensitive):
  ThinkPad `T4xx`/`T5xx`/`X13`/`X1`/`P14s`/`L14`, Dell `Latitude \d{4}`,
  HP `EliteBook \d{3}`/`ProBook \d{3}`.
- Exclude if title+description contains: `defect`, `nefunctional`,
  `pe piese`, `pentru piese`, `pt piese`, `spart`, `crapat`,
  `nu porneste`.
- Text matching is always lowercase + diacritic-stripped
  (ă/â→a, î→i, ș/ş→s, ț/ţ→t).
- `config.yaml` (real credentials) is never committed — only
  `config.example.yaml` is.
- No BeautifulSoup / CSS-selector scraping — data comes from the
  `window.__PRERENDERED_STATE__` JSON blob (see spec's "Data source"
  section). A single `requests.get()` per run is sufficient.

---

## File Structure

```
olx_bot/
  __init__.py
  config.py       # load_config(path) -> dict
  scraper.py      # fetch_html(url, timeout=15) -> str
  parser.py       # extract_prerendered_state(html) -> dict
                  # parse_listings(html) -> list[dict]
  filters.py      # passes_hard_filters(listing, config) -> bool
                  # + normalize_text, contains_excluded_keyword,
                  #   matches_business_model, ram_ok, cpu_gen_ok, storage_ok
  scorer.py       # compute_score(title, description, price, reference_prices) -> dict
  db.py           # init_db(path) -> sqlite3.Connection
                  # is_seen(conn, listing_id) -> bool
                  # mark_seen(conn, listing_id, title, price, score_pct, seen_at) -> None
  notifier.py     # build_email(listing, model, score_pct) -> EmailMessage
                  # send_email(listing, model, score_pct, gmail_config) -> None
  main.py         # run(config_path="config.yaml") -> None
tests/
  test_parser.py
  test_filters.py
  test_scorer.py
  test_db.py
  test_notifier.py
  test_scraper.py
  test_main.py
config.example.yaml
requirements.txt
.gitignore
run.bat
README.md
```

---

### Task 1: Project scaffolding + config loader

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `config.example.yaml`
- Create: `olx_bot/__init__.py`
- Create: `olx_bot/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `config.load_config(path: str) -> dict` — later tasks read
  config values (`config["max_price"]`, `config["gmail"]`, etc.) from
  this dict, so keys must match `config.example.yaml` exactly.

- [ ] **Step 1: Create `requirements.txt`**

```
requests>=2.31
PyYAML>=6.0
pytest>=8.0
```

- [ ] **Step 2: Create `.gitignore`**

```
venv/
__pycache__/
*.pyc
.pytest_cache/
config.yaml
*.db
bot.log
failure_count.txt
```

- [ ] **Step 3: Create `config.example.yaml`**

```yaml
filter_url: "https://www.olx.ro/electronice-si-electrocasnice/laptop-calculator-gaming/laptopuri/?search%5Bfilter_float_price%3Ato%5D=1500&search%5Border%5D=created_at%3Adesc"
max_price: 1500
db_path: "seen_listings.db"

reference_prices:
  "ThinkPad T480": 1800
  "ThinkPad T490": 2000
  "ThinkPad T14": 2200
  "ThinkPad X13": 2100
  "ThinkPad P14s": 2400
  "Latitude 5490": 1600
  "EliteBook 840": 1700

gmail:
  address: "your_email@gmail.com"
  app_password: "your_16_char_app_password"
  to: "your_email@gmail.com"
```

- [ ] **Step 4: Create `olx_bot/__init__.py`** (empty file)

- [ ] **Step 5: Write the failing test**

```python
# tests/test_config.py
import textwrap

from olx_bot.config import load_config


def test_load_config_reads_yaml(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        textwrap.dedent(
            """
            max_price: 1500
            gmail:
              address: "a@gmail.com"
            """
        )
    )
    config = load_config(str(config_path))
    assert config["max_price"] == 1500
    assert config["gmail"]["address"] == "a@gmail.com"
```

- [ ] **Step 6: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'olx_bot.config'`

- [ ] **Step 7: Write minimal implementation**

```python
# olx_bot/config.py
import yaml


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
```

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add requirements.txt .gitignore config.example.yaml olx_bot/__init__.py olx_bot/config.py tests/test_config.py
git commit -m "feat: add project scaffolding and config loader"
```

---

### Task 2: Parser (extract listings from embedded JSON state)

**Files:**
- Create: `olx_bot/parser.py`
- Test: `tests/test_parser.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `parser.extract_prerendered_state(html: str) -> dict`
  - `parser.parse_listings(html: str) -> list[dict]`, each dict shaped:
    `{"id": str, "title": str, "description": str, "price": int | None,
    "url": str, "location": str, "created_time": str, "params": dict[str, str]}`
  - Later tasks (`filters`, `scorer`, `main`) consume listing dicts in
    exactly this shape.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_parser.py
import json

from olx_bot.parser import extract_prerendered_state, parse_listings

SAMPLE_STATE = {
    "listing": {
        "listing": {
            "ads": [
                {
                    "id": 111,
                    "title": "Laptop Lenovo ThinkPad T480 i5-8350U",
                    "description": "SSD 256GB, 16GB RAM",
                    "url": "https://www.olx.ro/d/oferta/test-111.html",
                    "createdTime": "2026-09-01T10:00:00+03:00",
                    "location": {"pathName": "Bucuresti"},
                    "price": {"regularPrice": {"value": 1200}},
                    "params": [
                        {"key": "tip_stocare", "value": "SSD"},
                        {"key": "capacitate_memorie_ram", "value": "12 - 16 GB"},
                    ],
                },
                {
                    "id": 222,
                    "title": "Laptop schimb / gratis",
                    "description": "",
                    "url": "https://www.olx.ro/d/oferta/test-222.html",
                    "createdTime": "2026-09-01T11:00:00+03:00",
                    "location": {"pathName": "Cluj"},
                    "price": {"free": True},
                    "params": [],
                },
            ]
        }
    }
}


def _build_html(state: dict) -> str:
    js_literal = json.dumps(json.dumps(state))
    return f"<html><script>window.__PRERENDERED_STATE__ = {js_literal};\n</script></html>"


def test_extract_prerendered_state_roundtrip():
    html = _build_html(SAMPLE_STATE)
    result = extract_prerendered_state(html)
    assert result == SAMPLE_STATE


def test_extract_prerendered_state_missing_raises():
    try:
        extract_prerendered_state("<html>no state here</html>")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_parse_listings_extracts_fields():
    html = _build_html(SAMPLE_STATE)
    listings = parse_listings(html)
    assert len(listings) == 2

    first = listings[0]
    assert first["id"] == "111"
    assert first["title"] == "Laptop Lenovo ThinkPad T480 i5-8350U"
    assert first["price"] == 1200
    assert first["location"] == "Bucuresti"
    assert first["params"]["tip_stocare"] == "SSD"
    assert first["params"]["capacitate_memorie_ram"] == "12 - 16 GB"

    second = listings[1]
    assert second["id"] == "222"
    assert second["price"] is None
    assert second["params"] == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_parser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'olx_bot.parser'`

- [ ] **Step 3: Write minimal implementation**

```python
# olx_bot/parser.py
import json
import re

_STATE_RE = re.compile(r'window\.__PRERENDERED_STATE__\s*=\s*"(.*)";\s*\n')


def extract_prerendered_state(html: str) -> dict:
    match = _STATE_RE.search(html)
    if not match:
        raise ValueError("window.__PRERENDERED_STATE__ not found in page HTML")
    js_string = '"' + match.group(1) + '"'
    return json.loads(json.loads(js_string))


def parse_listings(html: str) -> list[dict]:
    state = extract_prerendered_state(html)
    ads = state["listing"]["listing"]["ads"]

    listings = []
    for ad in ads:
        price_info = ad.get("price") or {}
        regular = price_info.get("regularPrice")
        price = regular["value"] if regular else None

        params = {p["key"]: p.get("value") for p in ad.get("params", [])}

        listings.append(
            {
                "id": str(ad["id"]),
                "title": ad.get("title", ""),
                "description": ad.get("description", ""),
                "price": price,
                "url": ad.get("url", ""),
                "location": (ad.get("location") or {}).get("pathName", ""),
                "created_time": ad.get("createdTime", ""),
                "params": params,
            }
        )
    return listings
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_parser.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add olx_bot/parser.py tests/test_parser.py
git commit -m "feat: parse OLX listings from embedded prerendered state JSON"
```

---

### Task 3: Hard filters

**Files:**
- Create: `olx_bot/filters.py`
- Test: `tests/test_filters.py`

**Interfaces:**
- Consumes: listing dicts shaped as produced by `parser.parse_listings`
  (`title`, `description`, `price`, `params`).
- Produces: `filters.passes_hard_filters(listing: dict, config: dict) -> bool`.
  `main.py` (Task 8) calls this directly. `config` only needs to provide
  `max_price` for this task's purposes.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_filters.py
from olx_bot.filters import passes_hard_filters

CONFIG = {"max_price": 1500}


def qualifying_listing(**overrides):
    listing = {
        "title": "Laptop Lenovo ThinkPad T14 i5-1135G7",
        "description": "16GB RAM DDR4, SSD 512GB, stare impecabila",
        "price": 1200,
        "params": {
            "tip_stocare": "SSD",
            "capacitate_memorie_ram": "> 16 GB",
        },
    }
    listing.update(overrides)
    return listing


def test_qualifying_listing_passes():
    assert passes_hard_filters(qualifying_listing(), CONFIG) is True


def test_excludes_defective():
    listing = qualifying_listing(
        description="Vandut pentru piese, nu porneste"
    )
    assert passes_hard_filters(listing, CONFIG) is False


def test_excludes_non_business_model():
    listing = qualifying_listing(title="Laptop Asus X515 i5-1135G7")
    assert passes_hard_filters(listing, CONFIG) is False


def test_excludes_low_ram_bucket():
    listing = qualifying_listing(
        params={"tip_stocare": "SSD", "capacitate_memorie_ram": "8 - 12 GB"}
    )
    assert passes_hard_filters(listing, CONFIG) is False


def test_excludes_old_cpu():
    listing = qualifying_listing(
        title="Laptop Lenovo ThinkPad T14 i5-6200U",
        description="8GB RAM, SSD 256GB",
    )
    assert passes_hard_filters(listing, CONFIG) is False


def test_excludes_hdd_only():
    listing = qualifying_listing(
        params={"tip_stocare": "HDD", "capacitate_memorie_ram": "> 16 GB"}
    )
    assert passes_hard_filters(listing, CONFIG) is False


def test_excludes_over_price():
    listing = qualifying_listing(price=1600)
    assert passes_hard_filters(listing, CONFIG) is False


def test_ambiguous_ram_bucket_passes_with_explicit_mention():
    listing = qualifying_listing(
        description="16GB RAM DDR4, SSD 512GB",
        params={"tip_stocare": "SSD", "capacitate_memorie_ram": "12 - 16 GB"},
    )
    assert passes_hard_filters(listing, CONFIG) is True


def test_ambiguous_ram_bucket_fails_without_explicit_mention():
    listing = qualifying_listing(
        description="RAM generoasa, SSD 512GB",
        params={"tip_stocare": "SSD", "capacitate_memorie_ram": "12 - 16 GB"},
    )
    assert passes_hard_filters(listing, CONFIG) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_filters.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'olx_bot.filters'`

- [ ] **Step 3: Write minimal implementation**

```python
# olx_bot/filters.py
import re

_EXCLUDED_KEYWORDS = [
    "defect",
    "nefunctional",
    "pe piese",
    "pentru piese",
    "pt piese",
    "spart",
    "crapat",
    "nu porneste",
]

_BUSINESS_MODEL_PATTERNS = [
    r"\bt4[0-9]0\b",
    r"\bt5[0-9]0\b",
    r"\bx13\b",
    r"\bx1\b",
    r"\bp14s\b",
    r"\bl14\b",
    r"\blatitude ?\d{4}\b",
    r"\belitebook ?\d{3}\b",
    r"\bprobook ?\d{3}\b",
]

_CPU_GEN_PATTERNS = [
    r"\bi[3579]-1[1-3]\d{2}\b",
    r"\bgen(?:eratia)? ?1[1-3]\b",
    r"\bryzen [5-9] ?pro ?(5|6|7)\d{3}\b",
]

_DIACRITIC_MAP = str.maketrans("ăâîșşțţ", "aaisstt")


def normalize_text(text: str) -> str:
    return text.lower().translate(_DIACRITIC_MAP)


def contains_excluded_keyword(text: str) -> bool:
    normalized = normalize_text(text)
    return any(keyword in normalized for keyword in _EXCLUDED_KEYWORDS)


def matches_business_model(text: str) -> bool:
    normalized = normalize_text(text)
    return any(re.search(pattern, normalized) for pattern in _BUSINESS_MODEL_PATTERNS)


def ram_ok(params: dict, text: str) -> bool:
    bucket = params.get("capacitate_memorie_ram", "")
    if bucket == "> 16 GB":
        return True
    if bucket == "12 - 16 GB":
        normalized = normalize_text(text)
        return bool(re.search(r"16\s*gb", normalized))
    return False


def cpu_gen_ok(text: str) -> bool:
    normalized = normalize_text(text)
    return any(re.search(pattern, normalized) for pattern in _CPU_GEN_PATTERNS)


def storage_ok(params: dict) -> bool:
    return params.get("tip_stocare") in ("SSD", "HDD+SSD")


def passes_hard_filters(listing: dict, config: dict) -> bool:
    price = listing.get("price")
    if price is None or price > config.get("max_price", 1500):
        return False

    text = f"{listing.get('title', '')} {listing.get('description', '')}"
    if contains_excluded_keyword(text):
        return False
    if not matches_business_model(text):
        return False

    params = listing.get("params", {})
    if not ram_ok(params, text):
        return False
    if not cpu_gen_ok(text):
        return False
    if not storage_ok(params):
        return False

    return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_filters.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add olx_bot/filters.py tests/test_filters.py
git commit -m "feat: add hard filters for business-class laptop deals"
```

---

### Task 4: Scorer

**Files:**
- Create: `olx_bot/scorer.py`
- Test: `tests/test_scorer.py`

**Interfaces:**
- Consumes: `title: str`, `description: str`, `price: int`,
  `reference_prices: dict[str, int]` (from `config["reference_prices"]`).
- Produces: `scorer.compute_score(title, description, price, reference_prices) -> dict`
  shaped `{"model": str | None, "score_pct": float | None}`. `main.py`
  (Task 8) and `notifier.py` (Task 6) consume this shape.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scorer.py
import pytest

from olx_bot.scorer import compute_score

REFERENCE_PRICES = {"ThinkPad T480": 1800, "ThinkPad T14": 2200}


def test_compute_score_known_model():
    result = compute_score(
        "Laptop Lenovo ThinkPad T480 i5-8350U", "SSD 256GB", 1200, REFERENCE_PRICES
    )
    assert result["model"] == "ThinkPad T480"
    assert result["score_pct"] == pytest.approx((1800 - 1200) / 1800 * 100, abs=0.01)


def test_compute_score_unknown_model():
    result = compute_score("Laptop necunoscut XYZ", "", 900, REFERENCE_PRICES)
    assert result["model"] is None
    assert result["score_pct"] is None


def test_compute_score_matches_longest_description_too():
    result = compute_score(
        "Laptop business", "Model: ThinkPad T14, stare buna", 1500, REFERENCE_PRICES
    )
    assert result["model"] == "ThinkPad T14"
    assert result["score_pct"] == pytest.approx((2200 - 1500) / 2200 * 100, abs=0.01)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scorer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'olx_bot.scorer'`

- [ ] **Step 3: Write minimal implementation**

```python
# olx_bot/scorer.py


def _find_reference_price(text: str, reference_prices: dict) -> tuple[str, int] | None:
    lowered = text.lower()
    for model, price in reference_prices.items():
        if model.lower() in lowered:
            return model, price
    return None


def compute_score(
    title: str, description: str, price: int, reference_prices: dict
) -> dict:
    text = f"{title} {description}"
    match = _find_reference_price(text, reference_prices)
    if match is None:
        return {"model": None, "score_pct": None}

    model, reference_price = match
    score_pct = round((reference_price - price) / reference_price * 100, 1)
    return {"model": model, "score_pct": score_pct}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scorer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add olx_bot/scorer.py tests/test_scorer.py
git commit -m "feat: add deal-quality scorer against manual reference prices"
```

---

### Task 5: Deduplication DB

**Files:**
- Create: `olx_bot/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `db.init_db(path: str) -> sqlite3.Connection`
  - `db.is_seen(conn: sqlite3.Connection, listing_id: str) -> bool`
  - `db.mark_seen(conn: sqlite3.Connection, listing_id: str, title: str, price: int, score_pct: float | None, seen_at: str) -> None`
  - `main.py` (Task 8) calls all three.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db.py
from olx_bot.db import init_db, is_seen, mark_seen


def test_dedup_flow(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)

    assert is_seen(conn, "123") is False

    mark_seen(conn, "123", "Laptop Test", 1200, 33.3, "2026-09-02T10:00:00")

    assert is_seen(conn, "123") is True
    assert is_seen(conn, "999") is False

    conn.close()


def test_init_db_is_idempotent(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn1 = init_db(db_path)
    mark_seen(conn1, "1", "A", 100, None, "2026-09-02T10:00:00")
    conn1.close()

    conn2 = init_db(db_path)
    assert is_seen(conn2, "1") is True
    conn2.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'olx_bot.db'`

- [ ] **Step 3: Write minimal implementation**

```python
# olx_bot/db.py
import sqlite3


def init_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seen_listings (
            id TEXT PRIMARY KEY,
            title TEXT,
            price INTEGER,
            score_pct REAL,
            seen_at TEXT
        )
        """
    )
    conn.commit()
    return conn


def is_seen(conn: sqlite3.Connection, listing_id: str) -> bool:
    cursor = conn.execute(
        "SELECT 1 FROM seen_listings WHERE id = ?", (listing_id,)
    )
    return cursor.fetchone() is not None


def mark_seen(
    conn: sqlite3.Connection,
    listing_id: str,
    title: str,
    price: int,
    score_pct,
    seen_at: str,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO seen_listings (id, title, price, score_pct, seen_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (listing_id, title, price, score_pct, seen_at),
    )
    conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_db.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add olx_bot/db.py tests/test_db.py
git commit -m "feat: add sqlite-backed deduplication for seen listings"
```

---

### Task 6: Email notifier

**Files:**
- Create: `olx_bot/notifier.py`
- Test: `tests/test_notifier.py`

**Interfaces:**
- Consumes: listing dicts (`title`, `price`, `location`, `created_time`,
  `url`) from `parser.parse_listings`; `model`/`score_pct` from
  `scorer.compute_score`; `gmail_config: dict` shaped
  `{"address": str, "app_password": str, "to": str}` from
  `config["gmail"]`.
- Produces: `notifier.send_email(listing, model, score_pct, gmail_config) -> None`.
  `main.py` (Task 8) calls this for every new qualifying listing, and
  once more (with a synthetic listing) for the "bot is down" alert.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_notifier.py
from unittest.mock import MagicMock, patch

from olx_bot.notifier import build_email, send_email

LISTING = {
    "title": "Laptop Lenovo ThinkPad T480",
    "price": 1200,
    "location": "Bucuresti",
    "created_time": "2026-09-02T10:00:00+03:00",
    "url": "https://www.olx.ro/d/oferta/test.html",
}

GMAIL_CONFIG = {
    "address": "sender@gmail.com",
    "app_password": "app-pass",
    "to": "receiver@gmail.com",
}


def test_build_email_with_score():
    msg = build_email(LISTING, "ThinkPad T480", 33.3)
    assert "33.3%" in msg["Subject"]
    assert "ThinkPad T480" in msg["Subject"]
    body = msg.get_payload()
    assert LISTING["url"] in body


def test_build_email_without_score():
    msg = build_email(LISTING, None, None)
    assert "scor indisponibil" in msg["Subject"]


def test_send_email_uses_smtp_with_starttls():
    with patch("olx_bot.notifier.smtplib.SMTP") as mock_smtp_cls:
        smtp_instance = mock_smtp_cls.return_value.__enter__.return_value
        send_email(LISTING, "ThinkPad T480", 33.3, GMAIL_CONFIG)

        mock_smtp_cls.assert_called_once_with("smtp.gmail.com", 587, timeout=15)
        smtp_instance.starttls.assert_called_once()
        smtp_instance.login.assert_called_once_with("sender@gmail.com", "app-pass")
        assert smtp_instance.sendmail.call_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_notifier.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'olx_bot.notifier'`

- [ ] **Step 3: Write minimal implementation**

```python
# olx_bot/notifier.py
import smtplib
from email.mime.text import MIMEText


def build_email(listing: dict, model, score_pct) -> MIMEText:
    if score_pct is not None:
        subject = f"[OLX Deal] {model} - {listing['price']} lei ({score_pct}% sub referinta)"
        score_line = f"{score_pct}% sub referinta"
    else:
        subject = f"[OLX Deal] {listing['title']} - {listing['price']} lei (scor indisponibil)"
        score_line = "scor indisponibil (adauga pret referinta in config)"

    body = (
        f"Titlu: {listing['title']}\n"
        f"Pret: {listing['price']} lei\n"
        f"Scor: {score_line}\n"
        f"Locatie: {listing['location']}\n"
        f"Postat: {listing['created_time']}\n"
        f"Link: {listing['url']}\n"
    )

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    return msg


def send_email(listing: dict, model, score_pct, gmail_config: dict) -> None:
    msg = build_email(listing, model, score_pct)
    msg["From"] = gmail_config["address"]
    msg["To"] = gmail_config["to"]

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
        server.starttls()
        server.login(gmail_config["address"], gmail_config["app_password"])
        server.sendmail(gmail_config["address"], [gmail_config["to"]], msg.as_string())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_notifier.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add olx_bot/notifier.py tests/test_notifier.py
git commit -m "feat: add Gmail SMTP notifier for deal alerts"
```

---

### Task 7: Scraper (HTTP fetch)

**Files:**
- Create: `olx_bot/scraper.py`
- Test: `tests/test_scraper.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `scraper.fetch_html(url: str, timeout: int = 15) -> str`.
  `main.py` (Task 8) calls this, then pipes the result into
  `parser.parse_listings`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scraper.py
from unittest.mock import MagicMock, patch

from olx_bot.scraper import fetch_html


def test_fetch_html_returns_response_text():
    with patch("olx_bot.scraper.requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.text = "<html>ok</html>"
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = fetch_html("https://www.olx.ro/some-search/")

        assert result == "<html>ok</html>"
        mock_get.assert_called_once()
        _, kwargs = mock_get.call_args
        assert kwargs["timeout"] == 15
        assert "User-Agent" in kwargs["headers"]


def test_fetch_html_raises_on_http_error():
    with patch("olx_bot.scraper.requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("HTTP 503")
        mock_get.return_value = mock_response

        try:
            fetch_html("https://www.olx.ro/some-search/")
            assert False, "expected exception"
        except Exception as exc:
            assert "503" in str(exc)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scraper.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'olx_bot.scraper'`

- [ ] **Step 3: Write minimal implementation**

```python
# olx_bot/scraper.py
import requests

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def fetch_html(url: str, timeout: int = 15) -> str:
    response = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=timeout)
    response.raise_for_status()
    return response.text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scraper.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add olx_bot/scraper.py tests/test_scraper.py
git commit -m "feat: add OLX page fetcher"
```

---

### Task 8: Main orchestration, failure tracking, and deployment

**Files:**
- Create: `olx_bot/main.py`
- Create: `run.bat`
- Create: `README.md`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: every function produced in Tasks 1–7, exactly as named
  there (`config.load_config`, `scraper.fetch_html`,
  `parser.parse_listings`, `filters.passes_hard_filters`,
  `scorer.compute_score`, `db.init_db`/`is_seen`/`mark_seen`,
  `notifier.send_email`).
- Produces: `main.run(config_path: str = "config.yaml") -> None`, the
  script entry point invoked by `run.bat` via
  `python -m olx_bot.main`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_main.py
import json
from unittest.mock import patch

from olx_bot import main as main_module

SAMPLE_STATE = {
    "listing": {
        "listing": {
            "ads": [
                {
                    "id": 111,
                    "title": "Laptop Lenovo ThinkPad T14 i5-1135G7",
                    "description": "16GB RAM, SSD 512GB",
                    "url": "https://www.olx.ro/d/oferta/test-111.html",
                    "createdTime": "2026-09-02T10:00:00+03:00",
                    "location": {"pathName": "Bucuresti"},
                    "price": {"regularPrice": {"value": 1200}},
                    "params": [
                        {"key": "tip_stocare", "value": "SSD"},
                        {"key": "capacitate_memorie_ram", "value": "> 16 GB"},
                    ],
                },
                {
                    "id": 222,
                    "title": "Laptop Asus gaming ieftin",
                    "description": "8GB RAM, HDD",
                    "url": "https://www.olx.ro/d/oferta/test-222.html",
                    "createdTime": "2026-09-02T09:00:00+03:00",
                    "location": {"pathName": "Cluj"},
                    "price": {"regularPrice": {"value": 900}},
                    "params": [
                        {"key": "tip_stocare", "value": "HDD"},
                        {"key": "capacitate_memorie_ram", "value": "8 - 12 GB"},
                    ],
                },
            ]
        }
    }
}


def _fake_html():
    js_literal = json.dumps(json.dumps(SAMPLE_STATE))
    return f"<html><script>window.__PRERENDERED_STATE__ = {js_literal};\n</script></html>"


def _write_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
filter_url: "https://example.com/search"
max_price: 1500
db_path: "{tmp_path / 'seen.db'}"
reference_prices:
  "ThinkPad T14": 2200
gmail:
  address: "sender@gmail.com"
  app_password: "pw"
  to: "receiver@gmail.com"
"""
    )
    return str(config_path)


def test_run_emails_only_qualifying_new_listing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path)

    with patch("olx_bot.main.fetch_html", return_value=_fake_html()), patch(
        "olx_bot.main.send_email"
    ) as mock_send_email:
        main_module.run(config_path)

    assert mock_send_email.call_count == 1
    (listing_arg, model_arg, score_arg, gmail_arg), _ = mock_send_email.call_args
    assert listing_arg["id"] == "111"
    assert model_arg == "ThinkPad T14"
    assert gmail_arg["address"] == "sender@gmail.com"


def test_run_is_idempotent_on_second_pass(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path)

    with patch("olx_bot.main.fetch_html", return_value=_fake_html()), patch(
        "olx_bot.main.send_email"
    ) as mock_send_email:
        main_module.run(config_path)
        main_module.run(config_path)

    assert mock_send_email.call_count == 1


def test_run_logs_and_tracks_failure_on_scrape_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path)

    with patch("olx_bot.main.fetch_html", side_effect=Exception("network down")), patch(
        "olx_bot.main.send_email"
    ) as mock_send_email:
        main_module.run(config_path)

    assert mock_send_email.call_count == 0
    assert (tmp_path / main_module.FAILURE_STATE_PATH).read_text().strip() == "1"


def test_run_sends_down_alert_after_three_failures(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path)

    with patch("olx_bot.main.fetch_html", side_effect=Exception("network down")), patch(
        "olx_bot.main.send_email"
    ) as mock_send_email:
        main_module.run(config_path)
        main_module.run(config_path)
        main_module.run(config_path)

    assert mock_send_email.call_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_main.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'olx_bot.main'`

- [ ] **Step 3: Write minimal implementation**

```python
# olx_bot/main.py
import datetime
import logging
import os

from olx_bot.config import load_config
from olx_bot.db import init_db, is_seen, mark_seen
from olx_bot.filters import passes_hard_filters
from olx_bot.notifier import send_email
from olx_bot.parser import parse_listings
from olx_bot.scorer import compute_score
from olx_bot.scraper import fetch_html

FAILURE_STATE_PATH = "failure_count.txt"
FAILURE_ALERT_THRESHOLD = 3


def _read_failure_count() -> int:
    if not os.path.exists(FAILURE_STATE_PATH):
        return 0
    with open(FAILURE_STATE_PATH, "r", encoding="utf-8") as f:
        content = f.read().strip()
        return int(content) if content else 0


def _write_failure_count(count: int) -> None:
    with open(FAILURE_STATE_PATH, "w", encoding="utf-8") as f:
        f.write(str(count))


def run(config_path: str = "config.yaml") -> None:
    config = load_config(config_path)
    logging.basicConfig(
        filename="bot.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    try:
        html = fetch_html(config["filter_url"])
        listings = parse_listings(html)
    except Exception:
        logging.exception("Scrape/parse failed")
        failures = _read_failure_count() + 1
        _write_failure_count(failures)
        if failures == FAILURE_ALERT_THRESHOLD:
            down_listing = {
                "title": "Bot OLX oprit",
                "price": 0,
                "location": "",
                "created_time": "",
                "url": "",
            }
            send_email(down_listing, None, None, config["gmail"])
        return

    _write_failure_count(0)

    conn = init_db(config.get("db_path", "seen_listings.db"))
    try:
        for listing in listings:
            try:
                if is_seen(conn, listing["id"]):
                    continue
                if not passes_hard_filters(listing, config):
                    continue

                result = compute_score(
                    listing["title"],
                    listing["description"],
                    listing["price"],
                    config.get("reference_prices", {}),
                )
                send_email(listing, result["model"], result["score_pct"], config["gmail"])
                mark_seen(
                    conn,
                    listing["id"],
                    listing["title"],
                    listing["price"],
                    result["score_pct"],
                    datetime.datetime.now(datetime.timezone.utc).isoformat(),
                )
            except Exception:
                logging.exception("Failed processing listing %s", listing.get("id"))
    finally:
        conn.close()


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_main.py -v`
Expected: PASS

- [ ] **Step 5: Create `run.bat`**

```bat
@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
python -m olx_bot.main
```

- [ ] **Step 6: Create `README.md`**

```markdown
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
pytest -v
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
```

- [ ] **Step 7: Commit**

```bash
git add olx_bot/main.py tests/test_main.py run.bat README.md
git commit -m "feat: wire up main orchestration, failure alerting, and deployment docs"
```
