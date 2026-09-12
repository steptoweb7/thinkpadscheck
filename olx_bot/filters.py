import re

from olx_bot.db import get_price_stats

# Title-only matching: real listing descriptions are full of reseller boilerplate
# (trade-in offers, accessory lists, other-model mentions, upgrade pricing) that
# causes false matches/exclusions when combined with the title (found via live testing).

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
    r"\bt1[0-6]\b",
    r"\bx13\b",
    r"\bx1\b",
    r"\bp14s\b",
    r"\bl14\b",
    r"\blatitude ?\d{4}\b",
    r"\belitebook ?\d{3,4}\b",
    r"\bprobook ?\d{3,4}\b",
]

_CPU_GEN_PATTERNS = [
    r"\bi[3579]-1[1-9]\d{2}[a-z]?\d?\b",
    r"\bgen(?:eratia)? ?1[1-3]\b",
    r"\bryzen [5-9] ?pro ?(4|5|6|7|8|9)\d{3}\b",
    r"\bcore ultra [3579]\b",
]

# T480/T490 only ever shipped with 8th/9th-gen Intel CPUs -- the general
# gen-11+ bar would silently exclude them forever regardless of price.
# User explicitly asked for these two older models to be included too.
_LEGACY_GEN_MODEL_PATTERNS = [r"\bt480\b", r"\bt490\b"]
_LEGACY_CPU_GEN_PATTERN = r"\bi[3579]-[89]\d{3}[a-z]?\d?\b"

_PART_OUT_KEYWORDS = [
    "se negociaza separat",
    "pentru restul se negociaza",
    "restul se negociaza",
    "pretul este pentru carcasa",
    "pretul e pentru carcasa",
    "pretul este doar pentru",
    "pretul e doar pentru",
]

_CAPACITY_BUCKETS = [128, 256, 512, 1000, 2000, 4000, 8000]

_CAPACITY_PATTERN = r"\b(\d+(?:\.\d+)?)\s*(gb|tb)\b"
_MAX_PLAUSIBLE_CAPACITY_GB = 8000  # 8TB ceiling; larger matches are parsing noise, not real drives
_STORAGE_KEYWORD_PATTERN = re.compile(r"\b(ssd|hdd)\b")

_DIACRITIC_MAP = str.maketrans("ăâîșşțţ", "aaisstt")


def normalize_text(text: str) -> str:
    return text.lower().translate(_DIACRITIC_MAP)


def contains_excluded_keyword(text: str) -> bool:
    normalized = normalize_text(text)
    return any(keyword in normalized for keyword in _EXCLUDED_KEYWORDS)


def is_part_out_listing(text: str) -> bool:
    """True if the listed price only covers part of the machine and the
    rest (e.g. the drive) is negotiated separately — the advertised
    capacity isn't actually for sale at that price.

    Doesn't match on the bare word "dezmembr" alone: a seller offering
    optional disassembly on request ("la cerere pot sa il dezmembrez")
    for a complete, normally-priced system is not a part-out listing and
    was a real false-positive with an earlier version of this check.
    Only phrases that describe the *price* covering just part of the
    item count."""
    normalized = normalize_text(text)
    return any(keyword in normalized for keyword in _PART_OUT_KEYWORDS)


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
    if any(re.search(pattern, normalized) for pattern in _CPU_GEN_PATTERNS):
        return True

    is_legacy_gen_model = any(
        re.search(pattern, normalized) for pattern in _LEGACY_GEN_MODEL_PATTERNS
    )
    return is_legacy_gen_model and bool(re.search(_LEGACY_CPU_GEN_PATTERN, normalized))


def storage_ok(params: dict) -> bool:
    return params.get("tip_stocare") in ("SSD", "HDD+SSD")


def is_ssd(params: dict) -> bool:
    """SSD signal across two different OLX category schemas: laptops/PCs
    use "tip_stocare" (SSD/HDD/HDD+SSD); the standalone-drive category
    ("Componente Laptop-PC > Hard disk-uri") uses "tip" (SSD/HDD) instead,
    since a bare drive obviously isn't "half SSD, half HDD"."""
    return storage_ok(params) or params.get("tip") == "SSD"


def is_standalone_drive(params: dict) -> bool:
    """True for a bare drive listing (params schema uses "tip"), false
    for a laptop/PC-system listing (params schema uses "tip_stocare")."""
    return "tip" in params and "tip_stocare" not in params


def capacity_bucket(capacity_gb: int) -> int:
    """Snaps a real-world capacity (which varies seller to seller: 500 vs
    512, 960 vs 1000, etc.) to the nearest standard size, so prices for
    the "same" drive size can be pooled into one market-average bucket."""
    return min(_CAPACITY_BUCKETS, key=lambda bucket: abs(bucket - capacity_gb))


def extract_ssd_capacity_gb(text: str) -> int | None:
    """Best-effort SSD capacity extracted from free text (title/description).

    No structured OLX field reliably carries storage capacity across every
    category this rule scans, only storage TYPE. Doesn't require the
    number to sit next to the word "ssd" — real titles put a model number
    (e.g. "Kingston A400") between them, which broke an earlier version of
    this regex. Used only for the SSD-deal rule, which is explicitly a
    loose "any specs, just a cheap real SSD" scan, not the strict
    business-laptop rule — reading the description here is an accepted
    trade-off for that rule's purpose.

    Attributes each number to its NEAREST "ssd"/"hdd" keyword occurrence
    (by character distance) and drops numbers nearest an "hdd" mention —
    a real bug: a server listing with a 32GB boot SSD and a separate 3TB
    HDD for storage was reporting the HDD's 3TB as the SSD capacity,
    because a plain "take the largest GB/TB number in the text" doesn't
    know which drive a number belongs to. A number with no nearby
    keyword at all still counts (preserves matching for plain listings
    that never say "hdd" anywhere).
    """
    normalized = normalize_text(text)
    keyword_positions = [
        (m.start(), m.group(1)) for m in _STORAGE_KEYWORD_PATTERN.finditer(normalized)
    ]
    capacities = []
    for match in re.finditer(_CAPACITY_PATTERN, normalized):
        value_str, unit = match.group(1), match.group(2)
        value = float(value_str) * 1000 if unit == "tb" else float(value_str)
        if value > _MAX_PLAUSIBLE_CAPACITY_GB:
            continue

        nearest_keyword = None
        nearest_distance = None
        for pos, keyword in keyword_positions:
            distance = abs(pos - match.start())
            if nearest_distance is None or distance < nearest_distance:
                nearest_distance = distance
                nearest_keyword = keyword
        if nearest_keyword == "hdd":
            continue

        capacities.append(round(value))
    return max(capacities) if capacities else None


def passes_ssd_deal_filter(listing: dict, config: dict, conn=None) -> bool:
    """Laptop/PC listings (bundled system price) still use a flat
    ssd_deal.max_price — a whole system's price isn't a proxy for the
    drive's own market value. Standalone drive listings instead compare
    against a live market median built from previously observed
    standalone-drive prices at the same capacity_bucket (via `conn`):
    requires at least ssd_deal.min_samples observations at that bucket
    (a median from 1-2 ads is noise, not a market rate), then alerts only
    if the price is at or under ssd_deal.discount_threshold (default 0.6,
    i.e. 40%+ off) of that median.
    """
    if listing.get("is_business"):
        return False

    ssd_config = config.get("ssd_deal", {})
    params = listing.get("params", {})

    if not is_ssd(params):
        return False

    price = listing.get("price")
    if price is None:
        return False

    text = f"{listing.get('title', '')} {listing.get('description', '')}"
    if is_part_out_listing(text):
        return False

    capacity = extract_ssd_capacity_gb(text)
    if capacity is None or capacity < ssd_config.get("min_ssd_gb", 512):
        return False

    if is_standalone_drive(params):
        if conn is None:
            return False
        median, count = get_price_stats(conn, capacity_bucket(capacity))
        min_samples = ssd_config.get("min_samples", 5)
        if median is None or count < min_samples:
            return False
        discount_threshold = ssd_config.get("discount_threshold", 0.6)
        return price <= median * discount_threshold

    max_price = ssd_config.get("max_price", 800)
    return price <= max_price


def passes_hard_filters(listing: dict, config: dict) -> bool:
    if listing.get("is_business"):
        return False

    price = listing.get("price")
    if price is None or price > config.get("max_price", 1500):
        return False

    title_text = listing.get("title", "")
    if contains_excluded_keyword(title_text):
        return False
    if not matches_business_model(title_text):
        return False

    params = listing.get("params", {})
    if not ram_ok(params, title_text):
        return False
    if not cpu_gen_ok(title_text):
        return False
    if not storage_ok(params):
        return False

    return True
