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
