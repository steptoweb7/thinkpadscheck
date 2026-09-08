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
