import json

import pytest

from inbox_triage.classifier import (
    ClassifierError,
    SystemOneClassifier,
    build_state,
    require_local_url,
)
from tests.helpers import make_message

CATEGORIES = {"promotion": "Marketing", "personal": "Written by a human"}


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:8765", "http://localhost:8000/", "http://[::1]:8000"],
)
def test_local_urls_are_allowed(url) -> None:
    assert require_local_url(url) == url.rstrip("/")


@pytest.mark.parametrize(
    "url",
    [
        "https://api.typesafe.ai",
        "http://192.168.1.10:8000",
        "http://localhost.evil.example",
        "http://127.0.0.1.nip.io",
        "file:///etc/passwd",
    ],
)
def test_remote_urls_are_refused(url) -> None:
    with pytest.raises(ClassifierError):
        require_local_url(url)


def test_classify_sends_typed_questions_and_parses_answers() -> None:
    sent = {}

    def transport(url, body, headers, timeout):
        sent.update(url=url, payload=json.loads(body), headers=headers)
        return {
            "model": "von-latest",
            "answers": {
                "category": {
                    "type": "choice",
                    "choice": "promotion",
                    "probabilities": {"promotion": 0.91, "personal": 0.09},
                    "confidence": 0.8,
                },
                "needs_action": {"type": "noul", "noul": 0.18, "noul_raw": 0.05},
            },
            "usage": {"input_tokens": 50, "output_tokens": 0},
        }

    classifier = SystemOneClassifier(
        "http://127.0.0.1:8765", CATEGORIES, api_key="k", transport=transport
    )

    result = classifier.classify(make_message(subject="50% off"))

    assert sent["url"] == "http://127.0.0.1:8765/v1/systemone"
    assert sent["headers"]["Authorization"] == "Bearer k"
    assert sent["payload"]["questions"]["category"]["criteria"] == CATEGORIES
    assert sent["payload"]["questions"]["needs_action"]["type"] == "noul"
    assert "Subject: 50% off" in sent["payload"]["state"]
    assert result.category == "promotion"
    assert result.category_confidence == 0.91
    assert result.needs_action_probability == 0.05


def test_unknown_category_is_an_error() -> None:
    classifier = SystemOneClassifier(
        "http://127.0.0.1:8765",
        CATEGORIES,
        transport=lambda *_: {
            "answers": {"category": {"choice": "delete_everything", "confidence": 1}}
        },
    )

    with pytest.raises(ClassifierError, match="unknown category"):
        classifier.classify(make_message())


def test_state_truncates_snippet_and_flattens_whitespace() -> None:
    state = build_state(make_message(snippet="a\n\nb " + "x" * 2000))

    preview = state.split("Preview: ", 1)[1]
    assert preview.startswith("a b ")
    assert len(preview) == 500
