from unittest.mock import patch

from olx_bot.notifier import (
    build_email,
    build_specific_ssd_email,
    build_ssd_deal_email,
    send_email,
    send_specific_ssd_email,
    send_ssd_deal_email,
)

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
    body = msg.get_payload(decode=True).decode("utf-8")
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


def test_build_email_with_romanian_diacritics():
    """Test that Romanian diacritics (ă, â, î, ș, ț) are correctly encoded in UTF-8."""
    listing_with_diacritics = {
        "title": "Laptop Asus VivoBook cu înregistrare și ștergere sigură",
        "price": 1500,
        "location": "Brașov",
        "created_time": "2026-09-02T10:00:00+03:00",
        "url": "https://www.olx.ro/d/oferta/test.html",
    }

    # Build email with Romanian diacritics
    msg = build_email(listing_with_diacritics, "Asus VivoBook", 45.5)

    # Verify subject contains the model name with diacritics preserved
    assert "Asus VivoBook" in msg["Subject"]
    assert "45.5%" in msg["Subject"]

    # Verify body is UTF-8 encoded and contains diacritics
    body = msg.get_payload(decode=True).decode("utf-8")
    assert "Asus VivoBook cu înregistrare și ștergere sigură" in body
    assert "Brașov" in body
    assert listing_with_diacritics["url"] in body


def test_build_ssd_deal_email_subject_and_body():
    msg = build_ssd_deal_email(LISTING, 512, is_standalone_drive=False)
    assert "512GB" in msg["Subject"]
    assert "SSD" in msg["Subject"]
    assert str(LISTING["price"]) in msg["Subject"]
    body = msg.get_payload(decode=True).decode("utf-8")
    assert LISTING["url"] in body
    assert "512" in body


def test_build_ssd_deal_email_standalone_drive_uses_ssd_deal_label():
    """A bare-drive listing keeps the original [OLX SSD Deal] subject."""
    msg = build_ssd_deal_email(LISTING, 512, is_standalone_drive=True)
    assert msg["Subject"].startswith("[OLX SSD Deal]")


def test_build_ssd_deal_email_laptop_uses_distinct_label():
    """A laptop/PC listing that qualified via the SSD-deal rule must NOT
    look identical to a bare-drive deal in the inbox -- real complaint:
    user couldn't tell laptops and bare SSDs apart by subject alone."""
    msg = build_ssd_deal_email(LISTING, 512, is_standalone_drive=False)
    assert msg["Subject"].startswith("[OLX Laptop SSD Deal]")
    assert not msg["Subject"].startswith("[OLX SSD Deal]")


def test_send_ssd_deal_email_uses_smtp_with_starttls():
    with patch("olx_bot.notifier.smtplib.SMTP") as mock_smtp_cls:
        smtp_instance = mock_smtp_cls.return_value.__enter__.return_value
        send_ssd_deal_email(LISTING, 1000, GMAIL_CONFIG, is_standalone_drive=False)

        mock_smtp_cls.assert_called_once_with("smtp.gmail.com", 587, timeout=15)
        smtp_instance.starttls.assert_called_once()
        smtp_instance.login.assert_called_once_with("sender@gmail.com", "app-pass")
        assert smtp_instance.sendmail.call_count == 1


def test_build_specific_ssd_email_subject_and_body():
    msg = build_specific_ssd_email(LISTING, 512, "xg8")
    assert msg["Subject"].startswith("[SSD Specific]")
    assert "512" in msg["Subject"]
    assert str(LISTING["price"]) in msg["Subject"]
    body = msg.get_payload(decode=True).decode("utf-8")
    assert LISTING["url"] in body
    assert "XG8" in body


def test_send_specific_ssd_email_uses_smtp_with_starttls():
    with patch("olx_bot.notifier.smtplib.SMTP") as mock_smtp_cls:
        smtp_instance = mock_smtp_cls.return_value.__enter__.return_value
        send_specific_ssd_email(LISTING, 512, "pm9a1", GMAIL_CONFIG)

        mock_smtp_cls.assert_called_once_with("smtp.gmail.com", 587, timeout=15)
        smtp_instance.starttls.assert_called_once()
        smtp_instance.login.assert_called_once_with("sender@gmail.com", "app-pass")
        assert smtp_instance.sendmail.call_count == 1
