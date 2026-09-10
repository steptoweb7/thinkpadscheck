from curl_cffi import requests

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.olx.ro/",
}


def fetch_html(url: str, timeout: int = 15) -> str:
    """Fetch a page, impersonating Chrome's TLS fingerprint.

    Plain `requests` sends the right headers but a different TLS
    handshake signature than a real browser -- some anti-bot systems
    (seen live against OLX) fingerprint that and block it even when a
    real browser on the same IP loads fine. curl_cffi replicates
    Chrome's TLS ClientHello, not just its headers.
    """
    response = requests.get(url, headers=_HEADERS, timeout=timeout, impersonate="chrome124")
    response.raise_for_status()
    return response.text
