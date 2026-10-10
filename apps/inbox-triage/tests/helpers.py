from __future__ import annotations

from pathlib import Path

from gmail_core import GmailMessageMetadata

from inbox_triage.config import TriageConfig
from inbox_triage.models import Classification, InboxMessage

EXAMPLE_CONFIG = Path("config/triage.example.yaml")


def make_metadata(
    message_id: str = "m1",
    *,
    sender: str = "Shop <deals@shop.example>",
    subject: str = "Hello",
    snippet: str = "Preview text",
    label_ids: tuple[str, ...] = ("INBOX", "UNREAD", "CATEGORY_PERSONAL"),
    list_unsubscribe: str = "",
    list_id: str = "",
) -> GmailMessageMetadata:
    headers = {"from": sender, "subject": subject}
    if list_unsubscribe:
        headers["list-unsubscribe"] = list_unsubscribe
    if list_id:
        headers["list-id"] = list_id
    return GmailMessageMetadata(
        message_id=message_id,
        thread_id=f"t-{message_id}",
        label_ids=label_ids,
        snippet=snippet,
        internal_date_ms=1_760_000_000_000,
        headers=headers,
    )


def make_message(message_id: str = "m1", **kwargs) -> InboxMessage:
    return InboxMessage.from_metadata(make_metadata(message_id, **kwargs))


def example_config() -> TriageConfig:
    return TriageConfig.from_file(EXAMPLE_CONFIG)


class FakeMailbox:
    def __init__(self, messages: list[GmailMessageMetadata]):
        self.messages = {message.message_id: message for message in messages}
        self.queries: list[str] = []
        self.modified: list[tuple[str, list[str], list[str]]] = []
        self.trashed: list[str] = []
        self.labels_created: list[str] = []
        self.fail_ids: set[str] = set()

    def list_message_ids(self, query: str, limit: int | None = None) -> list[str]:
        self.queries.append(query)
        ids = list(self.messages)
        return ids[:limit] if limit else ids

    def get_message_metadata(self, message_id: str) -> GmailMessageMetadata:
        return self.messages[message_id]

    def ensure_label(self, label_name: str) -> str:
        self.labels_created.append(label_name)
        return "Label_processed"

    def modify_message(self, message_id, add_label_ids=None, remove_label_ids=None):
        if message_id in self.fail_ids:
            raise RuntimeError("boom")
        self.modified.append((message_id, add_label_ids or [], remove_label_ids or []))

    def trash_message(self, message_id: str) -> None:
        if message_id in self.fail_ids:
            raise RuntimeError("boom")
        self.trashed.append(message_id)


class FakeClassifier:
    def __init__(self, result: Classification | Exception):
        self.result = result
        self.calls: list[str] = []

    def classify(self, message: InboxMessage) -> Classification:
        self.calls.append(message.message_id)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result
