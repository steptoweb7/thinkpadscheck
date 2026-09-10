import re

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

_CAPACITY_PATTERN = r"\b(\d+(?:\.\d+)?)\s*(gb|tb)\b"
_MAX_PLAUSIBLE_CAPACITY_GB = 8000  # 8TB ceiling; larger matches are parsing noise, not real drives

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


def is_ssd(params: dict) -> bool:
    """SSD signal across two different OLX category schemas: laptops/PCs
    use "tip_stocare" (SSD/HDD/HDD+SSD); the standalone-drive category
    ("Componente Laptop-PC > Hard disk-uri") uses "tip" (SSD/HDD) instead,
    since a bare drive obviously isn't "half SSD, half HDD"."""
    return storage_ok(params) or params.get("tip") == "SSD"


def extract_ssd_capacity_gb(text: str) -> int | None:
    """Best-effort SSD capacity extracted from free text (title/description).

    No structured OLX field reliably carries storage capacity across every
    category this rule scans, only storage TYPE. Doesn't require the
    number to sit next to the word "ssd" — real titles put a model number
    (e.g. "Kingston A400") between them, which broke an earlier version of
    this regex. Used only for the SSD-deal rule, which is explicitly a
    loose "any specs, just a cheap real SSD" scan, not the strict
    business-laptop rule — reading the description here is an accepted
    trade-off for that rule's purpose. Takes the largest GB/TB mention,
    which in practice is the drive's capacity, not RAM (SSD capacities run
    much larger than RAM in nearly every real listing).
    """
    normalized = normalize_text(text)
    capacities = []
    for value_str, unit in re.findall(_CAPACITY_PATTERN, normalized):
        value = float(value_str) * 1000 if unit == "tb" else float(value_str)
        if value <= _MAX_PLAUSIBLE_CAPACITY_GB:
            capacities.append(round(value))
    return max(capacities) if capacities else None


def passes_ssd_deal_filter(listing: dict, config: dict) -> bool:
    if listing.get("is_business"):
        return False

    ssd_config = config.get("ssd_deal", {})

    price = listing.get("price")
    if price is None or price > ssd_config.get("max_price", 800):
        return False

    if not is_ssd(listing.get("params", {})):
        return False

    text = f"{listing.get('title', '')} {listing.get('description', '')}"
    capacity = extract_ssd_capacity_gb(text)
    if capacity is None or capacity < ssd_config.get("min_ssd_gb", 512):
        return False

    return True


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
