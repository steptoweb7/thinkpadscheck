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
