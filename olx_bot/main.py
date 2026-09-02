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
