import csv
import os

CSV_COLUMNS = [
    "timestamp",
    "rule",
    "listing_id",
    "title",
    "price_lei",
    "model",
    "score_pct",
    "ssd_capacity_gb",
    "location",
    "posted_at",
    "url",
]


def append_alert(csv_path: str, row: dict) -> None:
    file_exists = os.path.exists(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)
