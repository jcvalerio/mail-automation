from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parseaddr
from enum import StrEnum

from gmail_core import GmailMessageMetadata

GMAIL_CATEGORY_LABELS = {
    "CATEGORY_PERSONAL": "primary",
    "CATEGORY_PROMOTIONS": "promotions",
    "CATEGORY_UPDATES": "updates",
    "CATEGORY_FORUMS": "forums",
    "CATEGORY_SOCIAL": "social",
}


# Sender mailbox names that are never a person writing to you.
_AUTOMATED_LOCAL_PART_RE = re.compile(
    r"no-?reply|do-?not-?reply|noresponse|notifica|alerta|alerts?\b|mailer-daemon"
)


class Action(StrEnum):
    KEEP = "keep"
    ARCHIVE = "archive"
    TRASH = "trash"


class Priority(StrEnum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class DecisionSource(StrEnum):
    GUARD = "guard"
    RULE = "rule"
    MODEL = "model"
    UNCERTAIN = "uncertain"
    UNCLASSIFIED = "unclassified"


@dataclass(frozen=True)
class InboxMessage:
    message_id: str
    thread_id: str
    sender: str
    sender_email: str
    sender_domain: str
    subject: str
    snippet: str
    label_ids: tuple[str, ...]
    has_list_unsubscribe: bool
    list_id: str
    received_at: datetime | None

    @classmethod
    def from_metadata(cls, metadata: GmailMessageMetadata) -> InboxMessage:
        sender = metadata.header("From")
        _, address = parseaddr(sender)
        address = address.strip().lower()
        domain = address.rpartition("@")[2] if "@" in address else ""
        received_at = (
            datetime.fromtimestamp(metadata.internal_date_ms / 1000, tz=UTC)
            if metadata.internal_date_ms
            else None
        )
        return cls(
            message_id=metadata.message_id,
            thread_id=metadata.thread_id,
            sender=sender,
            sender_email=address,
            sender_domain=domain,
            subject=metadata.header("Subject"),
            snippet=metadata.snippet,
            label_ids=metadata.label_ids,
            has_list_unsubscribe=bool(metadata.header("List-Unsubscribe")),
            list_id=metadata.header("List-Id"),
            received_at=received_at,
        )

    @property
    def gmail_category(self) -> str:
        for label_id in self.label_ids:
            category = GMAIL_CATEGORY_LABELS.get(label_id)
            if category:
                return category
        return "primary"

    @property
    def is_starred(self) -> bool:
        return "STARRED" in self.label_ids

    @property
    def is_automated_sender(self) -> bool:
        local_part = self.sender_email.partition("@")[0]
        return self.has_list_unsubscribe or bool(
            _AUTOMATED_LOCAL_PART_RE.search(local_part)
        )


@dataclass(frozen=True)
class Classification:
    category: str
    category_confidence: float
    needs_action_probability: float | None = None
    probabilities: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class Decision:
    message: InboxMessage
    category: str
    action: Action
    priority: Priority
    source: DecisionSource
    reason: str
    rule_name: str | None = None
    confidence: float | None = None
    needs_action_probability: float | None = None
