from datetime import datetime, timedelta

import pytest

from inbox_triage.audit import classify_outcome, run_audit
from inbox_triage.models import Action, Decision, DecisionSource, Priority
from inbox_triage.store import DecisionStore
from tests.helpers import make_message

NOW = datetime.fromisoformat("2026-10-11T08:00:00-06:00")


@pytest.mark.parametrize(
    ("action", "labels", "outcome"),
    [
        ("trash", ("TRASH",), "ok"),
        ("trash", ("INBOX",), "rescued"),
        ("trash", ("CATEGORY_UPDATES",), "rescued"),
        ("trash", None, "gone"),
        ("archive", ("Label_1",), "ok"),
        ("archive", ("INBOX", "Label_1"), "rescued"),
        ("archive", ("TRASH",), "confirmed"),
        ("keep", ("INBOX", "UNREAD"), "ok"),
        ("keep", ("TRASH", "UNREAD"), "noise"),
        ("keep", ("UNREAD",), "noise"),
        ("keep", ("TRASH",), "confirmed"),
        ("keep", (), "confirmed"),
    ],
)
def test_classify_outcome(action, labels, outcome) -> None:
    assert classify_outcome(action, labels) == outcome


def _decision(message_id: str, action: Action) -> Decision:
    return Decision(
        message=make_message(message_id),
        category="newsletter",
        action=action,
        priority=Priority.LOW,
        source=DecisionSource.RULE,
        reason="test",
        rule_name="newsletters",
    )


class FakeLabels:
    def __init__(self, labels):
        self.labels = labels
        self.calls: list[str] = []

    def get_label_ids(self, message_id):
        self.calls.append(message_id)
        value = self.labels[message_id]
        if isinstance(value, Exception):
            raise value
        return value


def _store(tmp_path, decisions, run_at=NOW - timedelta(days=1), applied=True):
    store = DecisionStore(tmp_path / "triage.sqlite")
    ids = {d.message.message_id for d in decisions} if applied else set()
    store.record("run1", run_at.isoformat(), "apply", decisions, ids, {})
    return store


def test_audit_records_rescues_and_skips_final_outcomes(tmp_path) -> None:
    store = _store(
        tmp_path,
        [_decision("a", Action.TRASH), _decision("b", Action.ARCHIVE)],
    )
    mailbox = FakeLabels({"a": ("INBOX",), "b": ("Label_1",)})

    summary = run_audit(mailbox, store, NOW)

    assert summary.outcomes == {"rescued": 1, "ok": 1}
    assert store.audits()["a"].final is True
    assert store.audits()["b"].final is False

    run_audit(mailbox, store, NOW + timedelta(days=1))
    assert mailbox.calls == ["a", "b", "b"]  # "a" is final, not re-checked


def test_audit_ignores_dry_runs_and_messages_outside_window(tmp_path) -> None:
    store = _store(
        tmp_path, [_decision("old", Action.TRASH)], run_at=NOW - timedelta(days=40)
    )
    store.record(
        "dry",
        (NOW - timedelta(days=1)).isoformat(),
        "dry-run",
        [_decision("dry", Action.TRASH)],
        set(),
        {},
    )
    mailbox = FakeLabels({})

    summary = run_audit(mailbox, store, NOW)

    assert summary.checked == 0
    assert mailbox.calls == []


def test_audit_counts_gmail_errors_and_retries_later(tmp_path) -> None:
    store = _store(tmp_path, [_decision("a", Action.TRASH)])

    summary = run_audit(FakeLabels({"a": RuntimeError("quota")}), store, NOW)

    assert summary.errors == 1
    assert "a" not in store.audits()
