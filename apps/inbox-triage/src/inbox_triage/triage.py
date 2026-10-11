from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from gmail_core import GmailMessageMetadata

from inbox_triage.classifier import Classifier, ClassifierError
from inbox_triage.models import Action, Decision, InboxMessage
from inbox_triage.policy import Policy

INBOX_LABEL = "INBOX"


class Mailbox(Protocol):
    def list_message_ids(self, query: str, limit: int | None = None) -> list[str]: ...

    def get_message_metadata(self, message_id: str) -> GmailMessageMetadata: ...

    def ensure_label(self, label_name: str) -> str: ...

    def modify_message(
        self,
        message_id: str,
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> None: ...

    def trash_message(self, message_id: str) -> None: ...


@dataclass
class RunReport:
    run_id: str
    started_at: datetime
    apply: bool
    query: str
    decisions: list[Decision] = field(default_factory=list)
    applied_ids: set[str] = field(default_factory=set)
    errors: dict[str, str] = field(default_factory=dict)
    classifier_error: str | None = None
    skipped_already_handled: int = 0
    skipped_not_in_inbox: int = 0
    limit: int | None = None
    more_remaining: bool = False

    @property
    def mode(self) -> str:
        return "apply" if self.apply else "dry-run"


def run_triage(
    mailbox: Mailbox,
    policy: Policy,
    classifier: Classifier | None,
    *,
    query: str,
    processed_label: str,
    apply: bool,
    limit: int | None,
    already_handled: set[str],
    started_at: datetime | None = None,
) -> RunReport:
    started_at = started_at or datetime.now().astimezone()
    report = RunReport(
        run_id=started_at.strftime("%Y%m%dT%H%M%S%z"),
        started_at=started_at,
        apply=apply,
        query=query,
    )
    if classifier is None:
        report.classifier_error = "Classifier disabled"

    # Ask for one extra id so hitting the cap is reported, never silent.
    message_ids = mailbox.list_message_ids(query, limit + 1 if limit else None)
    if limit and len(message_ids) > limit:
        report.limit = limit
        report.more_remaining = True
        message_ids = message_ids[:limit]

    for message_id in message_ids:
        if apply and message_id in already_handled:
            report.skipped_already_handled += 1
            continue
        message = InboxMessage.from_metadata(mailbox.get_message_metadata(message_id))
        # Defense in depth: never act on anything outside the inbox, whatever
        # the search query returned.
        if INBOX_LABEL not in message.label_ids:
            report.skipped_not_in_inbox += 1
            continue
        report.decisions.append(_decide(policy, classifier, message, report))

    if apply:
        _apply(mailbox, report, processed_label)
    return report


def _decide(
    policy: Policy,
    classifier: Classifier | None,
    message: InboxMessage,
    report: RunReport,
) -> Decision:
    decision = policy.decide_by_guard_or_rule(message)
    if decision is not None:
        return decision
    if classifier is None or report.classifier_error:
        return policy.unclassified(message, "No classifier result")
    try:
        classification = classifier.classify(message)
    except ClassifierError as error:
        # Fail closed: stop calling the classifier and keep everything else.
        report.classifier_error = str(error)
        return policy.unclassified(message, "Classifier failed")
    return policy.decide_by_model(message, classification)


def _apply(mailbox: Mailbox, report: RunReport, processed_label: str) -> None:
    processed_label_id: str | None = None
    for decision in report.decisions:
        message_id = decision.message.message_id
        try:
            if decision.action is Action.ARCHIVE:
                processed_label_id = processed_label_id or mailbox.ensure_label(
                    processed_label
                )
                mailbox.modify_message(
                    message_id,
                    add_label_ids=[processed_label_id],
                    remove_label_ids=[INBOX_LABEL],
                )
            elif decision.action is Action.TRASH:
                mailbox.trash_message(message_id)
            report.applied_ids.add(message_id)
        except Exception as error:  # noqa: BLE001
            report.errors[message_id] = str(error)
