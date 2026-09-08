import datetime
import logging
import logging.handlers
import os

from olx_bot.config import load_config
from olx_bot.db import init_db, is_seen, mark_seen
from olx_bot.filters import passes_hard_filters
from olx_bot.notifier import send_email
from olx_bot.parser import parse_listings
from olx_bot.scorer import compute_score
from olx_bot.scraper import fetch_html

FAILURE_STATE_PATH = "failure_count.txt"
DOWN_ALERT_SENT_PATH = "down_alert_sent.txt"
FAILURE_ALERT_THRESHOLD = 3


def _read_failure_count() -> int:
    if not os.path.exists(FAILURE_STATE_PATH):
        return 0
    with open(FAILURE_STATE_PATH, "r", encoding="utf-8") as f:
        content = f.read().strip()
        if not content:
            return 0
        try:
            return int(content)
        except ValueError:
            return 0


def _write_failure_count(count: int) -> None:
    with open(FAILURE_STATE_PATH, "w", encoding="utf-8") as f:
        f.write(str(count))


def _down_alert_already_sent() -> bool:
    if not os.path.exists(DOWN_ALERT_SENT_PATH):
        return False
    with open(DOWN_ALERT_SENT_PATH, "r", encoding="utf-8") as f:
        return f.read().strip() == "1"


def _mark_down_alert_sent() -> None:
    with open(DOWN_ALERT_SENT_PATH, "w", encoding="utf-8") as f:
        f.write("1")


def _clear_down_alert_marker() -> None:
    if os.path.exists(DOWN_ALERT_SENT_PATH):
        os.remove(DOWN_ALERT_SENT_PATH)


def run(config_path: str = "config.yaml") -> None:
    logging.basicConfig(
        handlers=[
            logging.handlers.TimedRotatingFileHandler(
                filename="bot.log", when="D", backupCount=14
            )
        ],
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    config = load_config(config_path)

    try:
        html = fetch_html(config["filter_url"])
        listings = parse_listings(html)
    except Exception:
        logging.exception("Scrape/parse failed")
        failures = _read_failure_count() + 1
        _write_failure_count(failures)
        if failures >= FAILURE_ALERT_THRESHOLD and not _down_alert_already_sent():
            down_listing = {
                "title": "Bot OLX oprit",
                "price": 0,
                "location": "",
                "created_time": "",
                "url": "",
            }
            try:
                send_email(down_listing, None, None, config["gmail"])
            except Exception:
                logging.exception("Failed to send down-alert email")
            else:
                _mark_down_alert_sent()
        return

    logging.info("Fetched %d listings", len(listings))
    if len(listings) == 0:
        logging.warning(
            "Parsed 0 listings - check filter_url or whether OLX changed page structure"
        )

    _write_failure_count(0)
    _clear_down_alert_marker()

    conn = init_db(config.get("db_path", "seen_listings.db"))
    sent_count = 0
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
                sent_count += 1
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

    logging.info("Processed %d listings, %d new alerts sent", len(listings), sent_count)


if __name__ == "__main__":
    run()
