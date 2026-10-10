from dataclasses import dataclass, field


@dataclass(frozen=True)
class GmailMessage:
    message_id: str
    subject: str
    sender: str
    label_ids: list[str]
    text: str


@dataclass(frozen=True)
class GmailMessageMetadata:
    """Headers-only view of a message; the body is never downloaded."""

    message_id: str
    thread_id: str
    label_ids: tuple[str, ...]
    snippet: str
    internal_date_ms: int | None
    headers: dict[str, str] = field(default_factory=dict)

    def header(self, name: str) -> str:
        return self.headers.get(name.lower(), "")
