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
