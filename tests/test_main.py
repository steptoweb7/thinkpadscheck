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
db_path: "{tmp_path / 'seen.db'}"
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


def test_run_is_idempotent_on_second_pass(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path)

    with patch("olx_bot.main.fetch_html", return_value=_fake_html()), patch(
        "olx_bot.main.send_email"
    ) as mock_send_email:
        main_module.run(config_path)
        main_module.run(config_path)

    assert mock_send_email.call_count == 1


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
