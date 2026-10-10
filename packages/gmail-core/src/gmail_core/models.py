from dataclasses import dataclass


@dataclass(frozen=True)
class GmailMessage:
    message_id: str
    subject: str
    sender: str
    label_ids: list[str]
    text: str
