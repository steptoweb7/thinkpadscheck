import csv

from olx_bot.csv_log import CSV_COLUMNS, append_alert


def test_append_alert_creates_file_with_header(tmp_path):
    csv_path = str(tmp_path / "alerts_log.csv")

    append_alert(
        csv_path,
        {
            "timestamp": "2026-09-11T10:00:00+00:00",
            "rule": "business",
            "listing_id": "111",
            "title": "Laptop ThinkPad T14",
            "price_lei": 1200,
            "model": "ThinkPad T14",
            "score_pct": 33.3,
            "ssd_capacity_gb": "",
            "location": "Bucuresti",
            "posted_at": "2026-09-11T09:00:00+03:00",
            "url": "https://www.olx.ro/d/oferta/test-111.html",
        },
    )

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == CSV_COLUMNS
        rows = list(reader)

    assert len(rows) == 1
    assert rows[0]["listing_id"] == "111"
    assert rows[0]["rule"] == "business"
    assert rows[0]["model"] == "ThinkPad T14"
    assert rows[0]["price_lei"] == "1200"


def test_append_alert_appends_without_duplicating_header(tmp_path):
    csv_path = str(tmp_path / "alerts_log.csv")
    row = {col: "" for col in CSV_COLUMNS}

    append_alert(csv_path, {**row, "listing_id": "1"})
    append_alert(csv_path, {**row, "listing_id": "2"})

    with open(csv_path, newline="", encoding="utf-8") as f:
        lines = f.readlines()

    assert len(lines) == 3  # 1 header + 2 rows, no repeated header
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert [r["listing_id"] for r in rows] == ["1", "2"]


def test_append_alert_handles_ssd_deal_row(tmp_path):
    csv_path = str(tmp_path / "alerts_log.csv")

    append_alert(
        csv_path,
        {
            "timestamp": "2026-09-11T10:00:00+00:00",
            "rule": "ssd_deal",
            "listing_id": "333",
            "title": "SSD Samsung 512GB",
            "price_lei": 150,
            "model": "",
            "score_pct": "",
            "ssd_capacity_gb": 512,
            "location": "Timisoara",
            "posted_at": "2026-09-11T08:00:00+03:00",
            "url": "https://www.olx.ro/d/oferta/test-333.html",
        },
    )

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert rows[0]["rule"] == "ssd_deal"
    assert rows[0]["ssd_capacity_gb"] == "512"
    assert rows[0]["model"] == ""
