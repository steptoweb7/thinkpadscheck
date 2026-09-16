import datetime
import logging
import logging.handlers
import os

from olx_bot.config import load_config
from olx_bot.csv_log import append_alert
from olx_bot.db import init_db, is_seen, mark_seen, record_price_observation
from olx_bot.filters import (
    capacity_bucket,
    extract_ssd_capacity_gb,
    is_part_out_listing,
    is_ssd,
    is_standalone_drive,
    matches_enterprise_ssd_model,
    matches_specific_ssd_model,
    passes_enterprise_ssd_filter,
    passes_hard_filters,
    passes_specific_ssd_filter,
    passes_ssd_deal_filter,
    passes_x1_yoga_wqhd_filter,
)
from olx_bot.notifier import (
    send_email,
    send_enterprise_ssd_email,
    send_specific_ssd_email,
    send_ssd_deal_email,
    send_x1_yoga_wqhd_email,
)
from olx_bot.parser import parse_listings
from olx_bot.scorer import compute_score
from olx_bot.scraper import fetch_html

CSV_LOG_PATH = "alerts_log.csv"
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


def _paginated_url(base_url: str, page: int) -> str:
    if page <= 1:
        return base_url
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}page={page}"


def _fetch_all_pages(base_url: str, pages: int) -> list:
    """Fetches `pages` pages of one category (OLX's own listing pages,
    not this bot's pagination) -- by default only page 1 (~50 listings)
    is scanned, which can silently miss older-but-still-new listings
    when more than that many appear within an hour."""
    listings = []
    for page in range(1, pages + 1):
        html = fetch_html(_paginated_url(base_url, page))
        listings.extend(parse_listings(html))
    return listings


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
    ssd_deal_config = config.get("ssd_deal", {})
    ssd_deal_urls = ssd_deal_config.get("filter_urls", [])

    pages = config.get("pages_per_category", 1)

    try:
        listings = _fetch_all_pages(config["filter_url"], pages)

        ssd_deal_listings = []
        for ssd_url in ssd_deal_urls:
            ssd_deal_listings.extend(_fetch_all_pages(ssd_url, pages))
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

    logging.info("Fetched %d listings, %d ssd-deal listings", len(listings), len(ssd_deal_listings))
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
            db_key = f"biz:{listing['id']}"
            try:
                if is_seen(conn, db_key):
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
                now = datetime.datetime.now(datetime.timezone.utc).isoformat()
                mark_seen(conn, db_key, listing["title"], listing["price"], result["score_pct"], now)
                append_alert(
                    config.get("csv_log_path", CSV_LOG_PATH),
                    {
                        "timestamp": now,
                        "rule": "business",
                        "listing_id": listing["id"],
                        "title": listing["title"],
                        "price_lei": listing["price"],
                        "model": result["model"] or "",
                        "score_pct": result["score_pct"] if result["score_pct"] is not None else "",
                        "ssd_capacity_gb": "",
                        "location": listing["location"],
                        "posted_at": listing["created_time"],
                        "url": listing["url"],
                    },
                )
            except Exception:
                logging.exception("Failed processing listing %s", listing.get("id"))

        seen_ssd_ids_this_run = set()
        for listing in ssd_deal_listings:
            ad_id = listing["id"]
            if ad_id in seen_ssd_ids_this_run:
                continue
            seen_ssd_ids_this_run.add(ad_id)

            db_key = f"ssd:{ad_id}"
            try:
                if is_seen(conn, db_key):
                    continue

                should_alert = passes_ssd_deal_filter(listing, config, conn)

                params = listing.get("params", {})
                if not listing.get("is_business") and is_ssd(params) and is_standalone_drive(params):
                    text = f"{listing.get('title', '')} {listing.get('description', '')}"
                    if not is_part_out_listing(text):
                        market_capacity = extract_ssd_capacity_gb(text)
                        market_price = listing.get("price")
                        if market_capacity is not None and market_price is not None:
                            record_price_observation(
                                conn,
                                str(ad_id),
                                capacity_bucket(market_capacity),
                                market_price,
                                datetime.datetime.now(datetime.timezone.utc).isoformat(),
                            )

                if not should_alert:
                    continue

                capacity_gb = extract_ssd_capacity_gb(
                    f"{listing['title']} {listing['description']}"
                )
                send_ssd_deal_email(
                    listing, capacity_gb, config["gmail"], is_standalone_drive(params)
                )
                sent_count += 1
                now = datetime.datetime.now(datetime.timezone.utc).isoformat()
                mark_seen(conn, db_key, listing["title"], listing["price"], None, now)
                append_alert(
                    config.get("csv_log_path", CSV_LOG_PATH),
                    {
                        "timestamp": now,
                        "rule": "ssd_deal",
                        "listing_id": ad_id,
                        "title": listing["title"],
                        "price_lei": listing["price"],
                        "model": "",
                        "score_pct": "",
                        "ssd_capacity_gb": capacity_gb if capacity_gb is not None else "",
                        "location": listing["location"],
                        "posted_at": listing["created_time"],
                        "url": listing["url"],
                    },
                )
            except Exception:
                logging.exception("Failed processing ssd-deal listing %s", ad_id)

        seen_specific_ssd_ids_this_run = set()
        for listing in listings + ssd_deal_listings:
            ad_id = listing["id"]
            if ad_id in seen_specific_ssd_ids_this_run:
                continue
            seen_specific_ssd_ids_this_run.add(ad_id)

            db_key = f"specific_ssd:{ad_id}"
            try:
                if is_seen(conn, db_key):
                    continue
                if not passes_specific_ssd_filter(listing, config):
                    continue

                text = f"{listing['title']} {listing['description']}"
                capacity_gb = extract_ssd_capacity_gb(text)
                model = matches_specific_ssd_model(text)
                send_specific_ssd_email(listing, capacity_gb, model, config["gmail"])
                sent_count += 1
                now = datetime.datetime.now(datetime.timezone.utc).isoformat()
                mark_seen(conn, db_key, listing["title"], listing["price"], None, now)
                append_alert(
                    config.get("csv_log_path", CSV_LOG_PATH),
                    {
                        "timestamp": now,
                        "rule": "specific_ssd",
                        "listing_id": ad_id,
                        "title": listing["title"],
                        "price_lei": listing["price"],
                        "model": model or "",
                        "score_pct": "",
                        "ssd_capacity_gb": capacity_gb if capacity_gb is not None else "",
                        "location": listing["location"],
                        "posted_at": listing["created_time"],
                        "url": listing["url"],
                    },
                )
            except Exception:
                logging.exception("Failed processing specific-ssd listing %s", ad_id)

        seen_enterprise_ssd_ids_this_run = set()
        for listing in listings + ssd_deal_listings:
            ad_id = listing["id"]
            if ad_id in seen_enterprise_ssd_ids_this_run:
                continue
            seen_enterprise_ssd_ids_this_run.add(ad_id)

            db_key = f"enterprise_ssd:{ad_id}"
            try:
                if is_seen(conn, db_key):
                    continue
                if not passes_enterprise_ssd_filter(listing, config):
                    continue

                text = f"{listing['title']} {listing['description']}"
                capacity_gb = extract_ssd_capacity_gb(text)
                model = matches_enterprise_ssd_model(text)
                send_enterprise_ssd_email(listing, capacity_gb, model, config["gmail"])
                sent_count += 1
                now = datetime.datetime.now(datetime.timezone.utc).isoformat()
                mark_seen(conn, db_key, listing["title"], listing["price"], None, now)
                append_alert(
                    config.get("csv_log_path", CSV_LOG_PATH),
                    {
                        "timestamp": now,
                        "rule": "enterprise_ssd",
                        "listing_id": ad_id,
                        "title": listing["title"],
                        "price_lei": listing["price"],
                        "model": model or "",
                        "score_pct": "",
                        "ssd_capacity_gb": capacity_gb if capacity_gb is not None else "",
                        "location": listing["location"],
                        "posted_at": listing["created_time"],
                        "url": listing["url"],
                    },
                )
            except Exception:
                logging.exception("Failed processing enterprise-ssd listing %s", ad_id)

        seen_x1_yoga_wqhd_ids_this_run = set()
        for listing in listings + ssd_deal_listings:
            ad_id = listing["id"]
            if ad_id in seen_x1_yoga_wqhd_ids_this_run:
                continue
            seen_x1_yoga_wqhd_ids_this_run.add(ad_id)

            db_key = f"x1_yoga_wqhd:{ad_id}"
            try:
                if is_seen(conn, db_key):
                    continue
                if not passes_x1_yoga_wqhd_filter(listing, config):
                    continue

                send_x1_yoga_wqhd_email(listing, config["gmail"])
                sent_count += 1
                now = datetime.datetime.now(datetime.timezone.utc).isoformat()
                mark_seen(conn, db_key, listing["title"], listing["price"], None, now)
                append_alert(
                    config.get("csv_log_path", CSV_LOG_PATH),
                    {
                        "timestamp": now,
                        "rule": "x1_yoga_wqhd",
                        "listing_id": ad_id,
                        "title": listing["title"],
                        "price_lei": listing["price"],
                        "model": "",
                        "score_pct": "",
                        "ssd_capacity_gb": "",
                        "location": listing["location"],
                        "posted_at": listing["created_time"],
                        "url": listing["url"],
                    },
                )
            except Exception:
                logging.exception("Failed processing x1-yoga-wqhd listing %s", ad_id)
    finally:
        conn.close()

    logging.info(
        "Processed %d listings, %d new alerts sent",
        len(listings) + len(ssd_deal_listings),
        sent_count,
    )


if __name__ == "__main__":
    run()
