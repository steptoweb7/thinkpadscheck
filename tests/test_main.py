import csv
import json
from unittest.mock import patch

from olx_bot import main as main_module

SAMPLE_STATE = {
    "listing": {
        "listing": {
            "ads": [
                {
                    "id": 111,
                    "title": "Laptop Lenovo ThinkPad T14 i5-1135G7",
                    "description": "16GB RAM, SSD 512GB",
                    "url": "https://www.olx.ro/d/oferta/test-111.html",
                    "createdTime": "2026-09-02T10:00:00+03:00",
                    "location": {"pathName": "Bucuresti"},
                    "price": {"regularPrice": {"value": 1200}},
                    "params": [
                        {"key": "tip_stocare", "value": "SSD"},
                        {"key": "capacitate_memorie_ram", "value": "> 16 GB"},
                    ],
                },
                {
                    "id": 222,
                    "title": "Laptop Asus gaming ieftin",
                    "description": "8GB RAM, HDD",
                    "url": "https://www.olx.ro/d/oferta/test-222.html",
                    "createdTime": "2026-09-02T09:00:00+03:00",
                    "location": {"pathName": "Cluj"},
                    "price": {"regularPrice": {"value": 900}},
                    "params": [
                        {"key": "tip_stocare", "value": "HDD"},
                        {"key": "capacitate_memorie_ram", "value": "8 - 12 GB"},
                    ],
                },
            ]
        }
    }
}


def _fake_html():
    js_literal = json.dumps(json.dumps(SAMPLE_STATE))
    return f"<html><script>window.__PRERENDERED_STATE__ = {js_literal};\n</script></html>"


def _write_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
filter_url: "https://example.com/search"
max_price: 1500
db_path: "{(tmp_path / 'seen.db').as_posix()}"
reference_prices:
  "ThinkPad T14": 2200
gmail:
  address: "sender@gmail.com"
  app_password: "pw"
  to: "receiver@gmail.com"
"""
    )
    return str(config_path)


def test_run_emails_only_qualifying_new_listing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path)

    with patch("olx_bot.main.fetch_html", return_value=_fake_html()), patch(
        "olx_bot.main.send_email"
    ) as mock_send_email:
        main_module.run(config_path)

    assert mock_send_email.call_count == 1
    (listing_arg, model_arg, score_arg, gmail_arg), _ = mock_send_email.call_args
    assert listing_arg["id"] == "111"
    assert model_arg == "ThinkPad T14"
    assert gmail_arg["address"] == "sender@gmail.com"

    with open(tmp_path / "alerts_log.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["rule"] == "business"
    assert rows[0]["listing_id"] == "111"
    assert rows[0]["model"] == "ThinkPad T14"
    assert rows[0]["price_lei"] == "1200"


def test_run_is_idempotent_on_second_pass(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path)

    with patch("olx_bot.main.fetch_html", return_value=_fake_html()), patch(
        "olx_bot.main.send_email"
    ) as mock_send_email:
        main_module.run(config_path)
        main_module.run(config_path)

    assert mock_send_email.call_count == 1

    with open(tmp_path / "alerts_log.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1  # CSV log doesn't duplicate rows for already-seen listings


def test_run_logs_and_tracks_failure_on_scrape_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path)

    with patch("olx_bot.main.fetch_html", side_effect=Exception("network down")), patch(
        "olx_bot.main.send_email"
    ) as mock_send_email:
        main_module.run(config_path)

    assert mock_send_email.call_count == 0
    assert (tmp_path / main_module.FAILURE_STATE_PATH).read_text().strip() == "1"


def test_run_sends_down_alert_after_three_failures(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path)

    with patch("olx_bot.main.fetch_html", side_effect=Exception("network down")), patch(
        "olx_bot.main.send_email"
    ) as mock_send_email:
        main_module.run(config_path)
        main_module.run(config_path)
        main_module.run(config_path)

    assert mock_send_email.call_count == 1


def test_down_alert_retries_after_send_failure_then_sends_once(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path)

    with patch("olx_bot.main.fetch_html", side_effect=Exception("network down")), patch(
        "olx_bot.main.send_email", side_effect=Exception("smtp down")
    ) as mock_send_email:
        main_module.run(config_path)
        main_module.run(config_path)
        main_module.run(config_path)
        # send_email kept raising, so the marker was never written and every
        # failure past the threshold retried the send.
        assert mock_send_email.call_count == 1
        main_module.run(config_path)
        assert mock_send_email.call_count == 2

    assert not main_module._down_alert_already_sent()

    # Now the outage recovers on the next attempt; simulate a working
    # send_email this time and confirm the marker resets after success.
    with patch("olx_bot.main.fetch_html", side_effect=Exception("network down")), patch(
        "olx_bot.main.send_email"
    ) as mock_send_email_ok:
        main_module.run(config_path)
        assert mock_send_email_ok.call_count == 1
        assert main_module._down_alert_already_sent()

        # Another failure after the alert was successfully sent should not
        # resend it.
        main_module.run(config_path)
        assert mock_send_email_ok.call_count == 1

    with patch("olx_bot.main.fetch_html", return_value=_fake_html()), patch(
        "olx_bot.main.send_email"
    ):
        main_module.run(config_path)

    assert not main_module._down_alert_already_sent()


def test_read_failure_count_survives_corrupt_state_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / main_module.FAILURE_STATE_PATH).write_text("not-a-number")

    assert main_module._read_failure_count() == 0


# --- second permanent rule: cheap real SSD (>=512GB), any specs, private sellers only ---

SSD_STATE = {
    "listing": {
        "listing": {
            "ads": [
                {
                    "id": 333,
                    "title": "Laptop HP i5-1035G1, 8GB, 512GB SSD",
                    "description": "Stare buna, functioneaza perfect",
                    "url": "https://www.olx.ro/d/oferta/test-333.html",
                    "createdTime": "2026-09-10T08:00:00+03:00",
                    "location": {"pathName": "Timisoara"},
                    "price": {"regularPrice": {"value": 700}},
                    "params": [{"key": "tip_stocare", "value": "SSD"}],
                },
                {
                    "id": 444,
                    "title": "Laptop vechi, HDD 500GB",
                    "description": "Stare buna",
                    "url": "https://www.olx.ro/d/oferta/test-444.html",
                    "createdTime": "2026-09-10T07:00:00+03:00",
                    "location": {"pathName": "Iasi"},
                    "price": {"regularPrice": {"value": 300}},
                    "params": [{"key": "tip_stocare", "value": "HDD"}],
                },
            ]
        }
    }
}


def _fake_ssd_html():
    js_literal = json.dumps(json.dumps(SSD_STATE))
    return f"<html><script>window.__PRERENDERED_STATE__ = {js_literal};\n</script></html>"


def _write_config_with_ssd_deal(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
filter_url: "https://example.com/search"
max_price: 1500
db_path: "{(tmp_path / 'seen.db').as_posix()}"
reference_prices:
  "ThinkPad T14": 2200
ssd_deal:
  filter_urls:
    - "https://example.com/ssd-search"
  max_price: 800
  min_ssd_gb: 512
gmail:
  address: "sender@gmail.com"
  app_password: "pw"
  to: "receiver@gmail.com"
"""
    )
    return str(config_path)


def _fetch_html_by_url(business_html, ssd_html):
    def _fake(url, *args, **kwargs):
        if url == "https://example.com/ssd-search":
            return ssd_html
        return business_html

    return _fake


def test_run_sends_ssd_deal_email_for_qualifying_listing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = _write_config_with_ssd_deal(tmp_path)

    with patch(
        "olx_bot.main.fetch_html",
        side_effect=_fetch_html_by_url(_fake_html(), _fake_ssd_html()),
    ), patch("olx_bot.main.send_email") as mock_send_email, patch(
        "olx_bot.main.send_ssd_deal_email"
    ) as mock_send_ssd_email:
        main_module.run(config_path)

    assert mock_send_email.call_count == 1  # unchanged business pipeline
    assert mock_send_ssd_email.call_count == 1
    (listing_arg, capacity_arg, gmail_arg), _ = mock_send_ssd_email.call_args
    assert listing_arg["id"] == "333"

    with open(tmp_path / "alerts_log.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    ssd_rows = [r for r in rows if r["rule"] == "ssd_deal"]
    assert len(ssd_rows) == 1
    assert ssd_rows[0]["listing_id"] == "333"
    assert ssd_rows[0]["ssd_capacity_gb"] == "512"
    assert ssd_rows[0]["model"] == ""
    assert capacity_arg == 512
    assert gmail_arg["address"] == "sender@gmail.com"


def test_run_ssd_deal_is_idempotent_on_second_pass(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = _write_config_with_ssd_deal(tmp_path)

    with patch(
        "olx_bot.main.fetch_html",
        side_effect=_fetch_html_by_url(_fake_html(), _fake_ssd_html()),
    ), patch("olx_bot.main.send_email"), patch(
        "olx_bot.main.send_ssd_deal_email"
    ) as mock_send_ssd_email:
        main_module.run(config_path)
        main_module.run(config_path)

    assert mock_send_ssd_email.call_count == 1


def test_run_ssd_deal_and_business_dedup_are_independent(tmp_path, monkeypatch):
    """The same ad id could theoretically qualify for both rules — each rule
    tracks its own seen-state, so both alerts fire independently."""
    shared_id_state = {
        "listing": {
            "listing": {
                "ads": [
                    {
                        "id": 111,
                        "title": "Laptop Lenovo ThinkPad T14 i5-1135G7",
                        "description": "16GB RAM, SSD 512GB",
                        "url": "https://www.olx.ro/d/oferta/test-111.html",
                        "createdTime": "2026-09-02T10:00:00+03:00",
                        "location": {"pathName": "Bucuresti"},
                        "price": {"regularPrice": {"value": 700}},
                        "params": [
                            {"key": "tip_stocare", "value": "SSD"},
                            {"key": "capacitate_memorie_ram", "value": "> 16 GB"},
                        ],
                    }
                ]
            }
        }
    }
    html = f"<html><script>window.__PRERENDERED_STATE__ = {json.dumps(json.dumps(shared_id_state))};\n</script></html>"

    monkeypatch.chdir(tmp_path)
    config_path = _write_config_with_ssd_deal(tmp_path)

    with patch(
        "olx_bot.main.fetch_html", side_effect=_fetch_html_by_url(html, html)
    ), patch("olx_bot.main.send_email") as mock_send_email, patch(
        "olx_bot.main.send_ssd_deal_email"
    ) as mock_send_ssd_email:
        main_module.run(config_path)

    assert mock_send_email.call_count == 1
    assert mock_send_ssd_email.call_count == 1
