"""Client for a localhost System One (TypeSafe-compatible) decision server.

Works with Von (`von serve`), Rizzo Flow, Kev, ollaya, or any server exposing
`POST /v1/systemone`. Remote hosts are refused so message metadata can never be
sent to a cloud service by misconfiguration.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any, Protocol
from urllib.parse import urlsplit

from inbox_triage.models import Classification, InboxMessage

LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
MAX_SNIPPET_CHARS = 500

NEEDS_ACTION_QUESTION = {
    "type": "noul",
    "instructions": (
        "Does the recipient personally need to do something because of this "
        "email, such as reply, pay, approve, review, fix, or attend?"
    ),
    "criteria": {
        "true": "A specific action from the recipient is requested or required",
        "false": "Informational, marketing, automated notice, or receipt only",
    },
}

Transport = Callable[[str, bytes, Mapping[str, str], float], dict[str, Any]]


class ClassifierError(RuntimeError):
    pass


class Classifier(Protocol):
    def classify(self, message: InboxMessage) -> Classification: ...


def require_local_url(base_url: str) -> str:
    parts = urlsplit(base_url)
    if parts.scheme not in {"http", "https"}:
        raise ClassifierError(f"Classifier URL must be http(s): {base_url}")
    if (parts.hostname or "").lower() not in LOCAL_HOSTS:
        raise ClassifierError(
            "Classifier URL must point to this machine "
            f"({', '.join(sorted(LOCAL_HOSTS))}); refusing {parts.hostname!r}"
        )
    return base_url.rstrip("/")


def build_state(message: InboxMessage) -> str:
    snippet = " ".join(message.snippet.split())[:MAX_SNIPPET_CHARS]
    return "\n".join(
        [
            f"From: {message.sender}",
            f"Subject: {message.subject}",
            f"Gmail tab: {message.gmail_category}",
            f"Has unsubscribe link: {'yes' if message.has_list_unsubscribe else 'no'}",
            f"Mailing list: {message.list_id or 'none'}",
            f"Preview: {snippet}",
        ]
    )


class SystemOneClassifier:
    def __init__(
        self,
        base_url: str,
        categories: Mapping[str, str],
        *,
        model: str = "von-latest",
        api_key: str | None = None,
        timeout: float = 30.0,
        transport: Transport | None = None,
    ):
        if not categories:
            raise ClassifierError("At least one category is required")
        self._url = f"{require_local_url(base_url)}/v1/systemone"
        self._categories = dict(categories)
        self._model = model
        self._api_key = api_key
        self._timeout = timeout
        self._transport = transport or _urllib_transport

    def classify(self, message: InboxMessage) -> Classification:
        payload = {
            "model": self._model,
            "state": build_state(message),
            "questions": {
                "category": {
                    "type": "choice",
                    "instructions": "Which category best describes this email?",
                    "criteria": self._categories,
                },
                "needs_action": NEEDS_ACTION_QUESTION,
            },
        }
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        response = self._transport(
            self._url, json.dumps(payload).encode("utf-8"), headers, self._timeout
        )
        return self._parse(response)

    def _parse(self, response: dict[str, Any]) -> Classification:
        try:
            answers = response["answers"]
            category_answer = answers["category"]
            category = category_answer["choice"]
        except (KeyError, TypeError) as error:
            raise ClassifierError(f"Malformed classifier response: {error}") from error
        if category not in self._categories:
            raise ClassifierError(f"Classifier returned unknown category {category!r}")

        probabilities = category_answer.get("probabilities") or {}
        confidence = probabilities.get(category, category_answer.get("confidence"))
        if confidence is None:
            raise ClassifierError("Classifier response has no category probability")

        needs_action = answers.get("needs_action") or {}
        needs_action_probability = needs_action.get(
            "noul_raw", needs_action.get("noul")
        )
        return Classification(
            category=category,
            category_confidence=float(confidence),
            needs_action_probability=None
            if needs_action_probability is None
            else float(needs_action_probability),
            probabilities={
                name: float(value)
                for name, value in probabilities.items()
                if name in self._categories
            },
        )


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ClassifierError(f"Classifier tried to redirect to {newurl}; refusing")


# No proxies (HTTP_PROXY env vars could route traffic off-box) and no redirects.
_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}), _RefuseRedirects()
)


def _urllib_transport(
    url: str, body: bytes, headers: Mapping[str, str], timeout: float
) -> dict[str, Any]:
    request = urllib.request.Request(
        url, data=body, headers=dict(headers), method="POST"
    )
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = _error_detail(error)
        raise ClassifierError(
            f"Classifier request failed: HTTP {error.code}: {detail}"
        ) from error
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ClassifierError(f"Classifier request failed: {error}") from error


def _error_detail(error: urllib.error.HTTPError, limit: int = 300) -> str:
    try:
        body = error.read().decode("utf-8", errors="replace")
    except OSError:
        return error.reason or "no detail"
    try:
        detail = json.loads(body).get("detail", body)
    except (json.JSONDecodeError, AttributeError):
        detail = body
    detail = " ".join(str(detail).split())
    return detail[:limit] or str(error.reason)
