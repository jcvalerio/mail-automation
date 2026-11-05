import json

import httplib2
import pytest
from googleapiclient.discovery import build

from gmail_core import GmailClient
from gmail_core.client import NUM_RETRIES


class FlakyHttp:
    """httplib2-compatible transport: times out `failures` times, then answers."""

    def __init__(self, failures: int, payload: dict):
        self.failures = failures
        self.payload = payload
        self.calls = 0

    def request(self, uri, method="GET", body=None, headers=None, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise TimeoutError("The read operation timed out")
        return httplib2.Response({"status": "200"}), json.dumps(self.payload).encode()


def _client(http: FlakyHttp) -> GmailClient:
    client = GmailClient.__new__(GmailClient)
    client._service = build("gmail", "v1", http=http, static_discovery=True)
    client._label_cache = None
    return client


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr("googleapiclient.http.time.sleep", lambda _seconds: None)


def test_read_timeout_is_retried():
    http = FlakyHttp(failures=1, payload={"id": "m1", "threadId": "t1"})

    metadata = _client(http).get_message_metadata("m1")

    assert metadata.message_id == "m1"
    assert http.calls == 2


def test_gives_up_after_num_retries():
    http = FlakyHttp(failures=NUM_RETRIES + 1, payload={})

    with pytest.raises(TimeoutError):
        _client(http).get_message_metadata("m1")
    assert http.calls == NUM_RETRIES + 1
