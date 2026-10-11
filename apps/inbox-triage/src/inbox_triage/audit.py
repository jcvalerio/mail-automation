"""Detect triage mistakes from what you did afterwards in Gmail.

Run daily. Gmail empties Trash after 30 days, so messages are only checked
while they are younger than AUDIT_WINDOW_DAYS; outcomes are kept forever in
the local log for the quarterly report.

Outcomes:
- rescued:    triage trashed/archived it, you moved it back (false positive).
- noise:      triage kept it, you trashed/archived it while still unread
              (a rule should have handled it).
- confirmed:  you agreed with the decision (read-then-filed a kept message,
              or trashed something triage archived).
- ok:         nothing changed yet; checked again on the next audit.
- gone:       Gmail no longer has the message (Trash emptied or deleted).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

from inbox_triage.store import AuditRow, DecisionStore, latest_by_message

AUDIT_WINDOW_DAYS = 25
FINAL_OUTCOMES = frozenset({"rescued", "noise", "confirmed", "gone"})


class LabelReader(Protocol):
    def get_label_ids(self, message_id: str) -> tuple[str, ...] | None: ...


@dataclass
class AuditSummary:
    checked: int = 0
    outcomes: Counter[str] = field(default_factory=Counter)
    errors: int = 0


def classify_outcome(action: str, labels: tuple[str, ...] | None) -> str:
    if labels is None:
        return "gone"
    in_inbox = "INBOX" in labels
    in_trash = "TRASH" in labels
    if action == "trash":
        return "ok" if in_trash else "rescued"
    if action == "archive":
        if in_inbox:
            return "rescued"
        return "confirmed" if in_trash else "ok"
    # keep
    if in_inbox and not in_trash:
        return "ok"
    return "noise" if "UNREAD" in labels else "confirmed"


def run_audit(
    mailbox: LabelReader, store: DecisionStore, now: datetime
) -> AuditSummary:
    summary = AuditSummary()
    cutoff = now - timedelta(days=AUDIT_WINDOW_DAYS)
    existing = store.audits()
    results: list[AuditRow] = []
    for message_id, decision in latest_by_message(
        store.decisions(), applied_only=True
    ).items():
        previous = existing.get(message_id)
        if previous and previous.final:
            continue
        if decision.run_at < cutoff:
            continue
        try:
            labels = mailbox.get_label_ids(message_id)
        except Exception:  # noqa: BLE001
            summary.errors += 1
            continue
        outcome = classify_outcome(decision.action, labels)
        summary.checked += 1
        summary.outcomes[outcome] += 1
        results.append(
            AuditRow(
                message_id=message_id,
                outcome=outcome,
                final=outcome in FINAL_OUTCOMES,
                checked_at=now,
                detected_at=now if outcome != "ok" else None,
            )
        )
    store.record_audits(results)
    return summary
