import smtplib
from email.mime.text import MIMEText


def build_email(listing: dict, model, score_pct) -> MIMEText:
    if score_pct is not None:
        subject = f"[OLX Deal] {model} - {listing['price']} lei ({score_pct}% sub referinta)"
        score_line = f"{score_pct}% sub referinta"
    else:
        subject = f"[OLX Deal] {listing['title']} - {listing['price']} lei (scor indisponibil)"
        score_line = "scor indisponibil (adauga pret referinta in config)"

    body = (
        f"Titlu: {listing['title']}\n"
        f"Pret: {listing['price']} lei\n"
        f"Scor: {score_line}\n"
        f"Locatie: {listing['location']}\n"
        f"Postat: {listing['created_time']}\n"
        f"Link: {listing['url']}\n"
    )

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    return msg


def build_ssd_deal_email(listing: dict, ssd_gb: int) -> MIMEText:
    subject = f"[OLX SSD Deal] {listing['title'][:60]} - {listing['price']} lei ({ssd_gb}GB SSD)"

    body = (
        f"Titlu: {listing['title']}\n"
        f"Pret: {listing['price']} lei\n"
        f"SSD detectat: {ssd_gb}GB (specificatiile de CPU/RAM nu conteaza pentru aceasta regula)\n"
        f"Locatie: {listing['location']}\n"
        f"Postat: {listing['created_time']}\n"
        f"Link: {listing['url']}\n"
    )

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    return msg


def _send(msg: MIMEText, gmail_config: dict) -> None:
    msg["From"] = gmail_config["address"]
    msg["To"] = gmail_config["to"]

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
        server.starttls()
        server.login(gmail_config["address"], gmail_config["app_password"])
        server.sendmail(gmail_config["address"], [gmail_config["to"]], msg.as_string())


def send_email(listing: dict, model, score_pct, gmail_config: dict) -> None:
    _send(build_email(listing, model, score_pct), gmail_config)


def send_ssd_deal_email(listing: dict, ssd_gb: int, gmail_config: dict) -> None:
    _send(build_ssd_deal_email(listing, ssd_gb), gmail_config)
