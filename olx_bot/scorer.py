

def _find_reference_price(text: str, reference_prices: dict) -> tuple[str, int] | None:
    lowered = text.lower()
    # Find all matching models, then return the longest one (most specific)
    matches = []
    for model, price in reference_prices.items():
        if model.lower() in lowered:
            matches.append((model, price))

    if not matches:
        return None

    # Prefer the longest model name (most specific match)
    best_match = max(matches, key=lambda m: len(m[0]))
    return best_match


def compute_score(
    title: str, description: str, price: int, reference_prices: dict
) -> dict:
    text = f"{title} {description}"
    match = _find_reference_price(text, reference_prices)
    if match is None:
        return {"model": None, "score_pct": None}

    model, reference_price = match
    # Guard against zero or falsy reference_price (malformed config)
    if not reference_price:
        return {"model": None, "score_pct": None}

    score_pct = round((reference_price - price) / reference_price * 100, 2)
    return {"model": model, "score_pct": score_pct}
