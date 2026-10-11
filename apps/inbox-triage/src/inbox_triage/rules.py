from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from inbox_triage.models import Action, InboxMessage, Priority


class RuleConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Rule:
    """All configured conditions must match (AND); values inside a list are OR."""

    name: str
    category: str
    action: Action | None = None
    priority: Priority | None = None
    sender_emails: tuple[str, ...] = ()
    sender_domains: tuple[str, ...] = ()
    subject_contains: tuple[str, ...] = ()
    subject_regex: re.Pattern[str] | None = None
    gmail_categories: tuple[str, ...] = ()
    list_id_contains: tuple[str, ...] = ()
    has_list_unsubscribe: bool | None = None
    older_than_days: int | None = None
    newer_than_days: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Rule:
        name = str(data.get("name") or "").strip()
        if not name:
            raise RuleConfigError("Every rule needs a name")
        category = str(data.get("category") or "").strip()
        if not category:
            raise RuleConfigError(f"Rule '{name}' needs a category")
        match = data.get("match") or {}
        if not match:
            raise RuleConfigError(f"Rule '{name}' needs at least one match condition")
        unknown = set(match) - _MATCH_KEYS
        if unknown:
            raise RuleConfigError(
                f"Rule '{name}' has unknown match keys: {', '.join(sorted(unknown))}"
            )
        subject_regex = match.get("subject_regex")
        has_list_unsubscribe = match.get("has_list_unsubscribe")
        older_than_days = match.get("older_than_days")
        newer_than_days = match.get("newer_than_days")
        return cls(
            name=name,
            category=category,
            action=Action(data["action"]) if data.get("action") else None,
            priority=Priority(data["priority"]) if data.get("priority") else None,
            sender_emails=_lowered(match.get("sender_emails")),
            sender_domains=_lowered(match.get("sender_domains")),
            subject_contains=_lowered(match.get("subject_contains")),
            subject_regex=re.compile(subject_regex, re.IGNORECASE)
            if subject_regex
            else None,
            gmail_categories=_lowered(match.get("gmail_categories")),
            list_id_contains=_lowered(match.get("list_id_contains")),
            has_list_unsubscribe=None
            if has_list_unsubscribe is None
            else bool(has_list_unsubscribe),
            older_than_days=_days(name, "older_than_days", older_than_days),
            newer_than_days=_days(name, "newer_than_days", newer_than_days),
        )

    def matches(self, message: InboxMessage, now: datetime | None = None) -> bool:
        subject = message.subject.casefold()
        checks = [
            not self.sender_emails or message.sender_email in self.sender_emails,
            not self.sender_domains
            or any(
                _domain_matches(message.sender_domain, domain)
                for domain in self.sender_domains
            ),
            not self.subject_contains
            or any(term in subject for term in self.subject_contains),
            self.subject_regex is None
            or self.subject_regex.search(message.subject) is not None,
            not self.gmail_categories
            or message.gmail_category in self.gmail_categories,
            not self.list_id_contains
            or any(
                term in message.list_id.casefold() for term in self.list_id_contains
            ),
            self.has_list_unsubscribe is None
            or message.has_list_unsubscribe == self.has_list_unsubscribe,
            self._age_matches(message, now),
        ]
        return all(checks)

    def _age_matches(self, message: InboxMessage, now: datetime | None) -> bool:
        if self.older_than_days is None and self.newer_than_days is None:
            return True
        if message.received_at is None:
            return False  # unknown age: never act on an age rule
        age = (now or datetime.now(UTC)).astimezone(UTC) - message.received_at
        if self.older_than_days is not None and age <= timedelta(
            days=self.older_than_days
        ):
            return False
        if self.newer_than_days is not None and age >= timedelta(
            days=self.newer_than_days
        ):
            return False
        return True


_MATCH_KEYS = {
    "sender_emails",
    "sender_domains",
    "subject_contains",
    "subject_regex",
    "gmail_categories",
    "list_id_contains",
    "has_list_unsubscribe",
    "older_than_days",
    "newer_than_days",
}


def first_matching_rule(
    rules: list[Rule], message: InboxMessage, now: datetime | None = None
) -> Rule | None:
    return next((rule for rule in rules if rule.matches(message, now)), None)


def _days(rule_name: str, key: str, value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RuleConfigError(f"Rule '{rule_name}': {key} must be a whole number >= 0")
    return value


def _domain_matches(actual: str, expected: str) -> bool:
    return actual == expected or actual.endswith(f".{expected}")


def _lowered(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        values = [values]
    return tuple(
        str(value).strip().casefold() for value in values if str(value).strip()
    )
