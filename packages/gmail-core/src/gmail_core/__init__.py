"""Shared local Gmail API access for mail-automation apps."""

from gmail_core.client import GMAIL_MODIFY_SCOPE, GmailClient, LabelResolutionError
from gmail_core.message_text import extract_message_text
from gmail_core.models import GmailMessage
from gmail_core.text import clean_text

__all__ = [
    "GMAIL_MODIFY_SCOPE",
    "GmailClient",
    "GmailMessage",
    "LabelResolutionError",
    "clean_text",
    "extract_message_text",
]
