from unittest.mock import MagicMock, patch

from olx_bot.notifier import build_email, send_email

LISTING = {
    "title": "Laptop Lenovo ThinkPad T480",
    "price": 1200,
    "location": "Bucuresti",
    "created_time": "2026-09-02T10:00:00+03:00",
    "url": "https://www.olx.ro/d/oferta/test.html",
}

GMAIL_CONFIG = {
    "address": "sender@gmail.com",
    "app_password": "app-pass",
    "to": "receiver@gmail.com",
}


def test_build_email_with_score():
    msg = build_email(LISTING, "ThinkPad T480", 33.3)
    assert "33.3%" in msg["Subject"]
    assert "ThinkPad T480" in msg["Subject"]
    body = msg.get_payload()
    assert LISTING["url"] in body


def test_build_email_without_score():
    msg = build_email(LISTING, None, None)
    assert "scor indisponibil" in msg["Subject"]


def test_send_email_uses_smtp_with_starttls():
    with patch("olx_bot.notifier.smtplib.SMTP") as mock_smtp_cls:
        smtp_instance = mock_smtp_cls.return_value.__enter__.return_value
        send_email(LISTING, "ThinkPad T480", 33.3, GMAIL_CONFIG)

        mock_smtp_cls.assert_called_once_with("smtp.gmail.com", 587, timeout=15)
        smtp_instance.starttls.assert_called_once()
        smtp_instance.login.assert_called_once_with("sender@gmail.com", "app-pass")
        assert smtp_instance.sendmail.call_count == 1
