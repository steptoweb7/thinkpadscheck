from unittest.mock import MagicMock, patch

from olx_bot.scraper import fetch_html


def test_fetch_html_returns_response_text():
    with patch("olx_bot.scraper.requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.text = "<html>ok</html>"
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = fetch_html("https://www.olx.ro/some-search/")

        assert result == "<html>ok</html>"
        mock_get.assert_called_once()
        _, kwargs = mock_get.call_args
        assert kwargs["timeout"] == 15
        headers = kwargs["headers"]
        assert "User-Agent" in headers
        assert "Accept" in headers
        assert "Accept-Language" in headers
        assert "Referer" in headers


def test_fetch_html_raises_on_http_error():
    with patch("olx_bot.scraper.requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("HTTP 503")
        mock_get.return_value = mock_response

        try:
            fetch_html("https://www.olx.ro/some-search/")
            assert False, "expected exception"
        except Exception as exc:
            assert "503" in str(exc)
