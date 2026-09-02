

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
    score_pct = round((reference_price - price) / reference_price * 100, 2)
    return {"model": model, "score_pct": score_pct}
