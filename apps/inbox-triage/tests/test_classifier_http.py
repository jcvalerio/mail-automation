import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from inbox_triage.classifier import ClassifierError, SystemOneClassifier
from tests.helpers import make_message

CATEGORIES = {"promotion": "Marketing", "other": "Anything else"}


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/broken/v1/systemone":
            data = json.dumps({"detail": "Failed to load weights"}).encode()
            self.send_response(422)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path == "/redirect/v1/systemone":
            self.send_response(307)
            self.send_header("Location", "http://example.com/v1/systemone")
            self.end_headers()
            return
        payload = {
            "model": body["model"],
            "answers": {
                "category": {
                    "choice": "promotion",
                    "probabilities": {"promotion": 0.97, "other": 0.03},
                    "confidence": 0.9,
                },
                "needs_action": {"noul": 0.2, "noul_raw": 0.04},
            },
            "usage": {"input_tokens": 1, "output_tokens": 0},
        }
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture
def server_url(monkeypatch):
    # A proxy env var must not divert localhost classifier traffic.
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:9")
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_real_http_round_trip_ignores_proxy_env(server_url) -> None:
    classifier = SystemOneClassifier(server_url, CATEGORIES, timeout=5)

    result = classifier.classify(make_message())

    assert result.category == "promotion"
    assert result.category_confidence == 0.97


def test_redirects_are_refused(server_url) -> None:
    classifier = SystemOneClassifier(f"{server_url}/redirect", CATEGORIES, timeout=5)

    with pytest.raises(ClassifierError):
        classifier.classify(make_message())


def test_http_error_includes_server_detail(server_url) -> None:
    classifier = SystemOneClassifier(f"{server_url}/broken", CATEGORIES, timeout=5)

    with pytest.raises(ClassifierError, match="HTTP 422: Failed to load weights"):
        classifier.classify(make_message())
