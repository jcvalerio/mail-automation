from base64 import urlsafe_b64encode

from gmail_core import clean_text, extract_message_text


def _encode(value: str) -> str:
    return urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def test_prefers_plain_text_over_html() -> None:
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/plain", "body": {"data": _encode("Plain body")}},
            {"mimeType": "text/html", "body": {"data": _encode("<p>HTML body</p>")}},
        ],
    }

    assert extract_message_text(payload) == "Plain body"


def test_falls_back_to_html_text() -> None:
    payload = {
        "mimeType": "text/html",
        "body": {"data": _encode("<div>Hola&nbsp;<b>mundo</b></div>")},
    }

    assert extract_message_text(payload) == "Hola \nmundo"


def test_returns_empty_string_without_text_parts() -> None:
    assert extract_message_text({"mimeType": "image/png", "body": {}}) == ""


def test_clean_text_strips_zero_width_and_normalizes_newlines() -> None:
    assert clean_text("\u200bA\r\nB\xa0C ") == "A\nB C"
