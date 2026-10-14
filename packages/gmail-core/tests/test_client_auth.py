import pytest

from gmail_core import GmailClient


def test_noninteractive_refuses_browser_login(tmp_path, monkeypatch):
    monkeypatch.setenv("GMAIL_NONINTERACTIVE", "1")

    with pytest.raises(RuntimeError, match="interactively"):
        GmailClient(tmp_path / "credentials.json", tmp_path / "token.json")
