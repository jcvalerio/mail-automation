import random
from datetime import datetime, timedelta

from inbox_triage.models import Action, Decision, DecisionSource, Priority
from inbox_triage.report import ReportSettings, render_report
from inbox_triage.store import AuditRow, DecisionStore
from tests.helpers import example_config, make_message

NOW = datetime.fromisoformat("2026-10-11T08:00:00-06:00")


def _decision(
    message_id,
    *,
    category="newsletter",
    action=Action.TRASH,
    source=DecisionSource.RULE,
    rule_name="social-networks",
    sender="a@news.example",
    subject="Weekly news",
    unsubscribe=False,
):
    return Decision(
        message=make_message(
            message_id,
            sender=sender,
            subject=subject,
            list_unsubscribe="<mailto:u@x.example>" if unsubscribe else "",
        ),
        category=category,
        action=action,
        priority=Priority.LOW,
        source=source,
        reason="test",
        rule_name=rule_name if source is DecisionSource.RULE else None,
    )


def _render(store, **settings):
    return render_report(
        store,
        example_config().policy,
        NOW,
        ReportSettings(**settings),
        random.Random(1),
    )


def _store(tmp_path, decisions, *, run_at=NOW - timedelta(days=2), applied=True):
    store = DecisionStore(tmp_path / "t.sqlite")
    ids = {d.message.message_id for d in decisions} if applied else set()
    store.record(
        "r1", run_at.isoformat(), "apply" if applied else "dry-run", decisions, ids, {}
    )
    return store


def test_rule_and_category_match_counts(tmp_path) -> None:
    store = _store(
        tmp_path,
        [
            _decision("a"),
            _decision("b"),
            _decision(
                "c", rule_name="statements", category="statement", action=Action.ARCHIVE
            ),
        ],
    )

    report = _render(store)

    assert "| social-networks | newsletter | 2 |" in report
    assert "| statements | statement | 1 |" in report
    assert "| risky-transactions | risky_transaction | 0 |" in report
    assert "| newsletter | 2 | 2 | 0 | trash 2 |" in report


def test_proposes_removing_only_old_unused_rules(tmp_path) -> None:
    store = _store(tmp_path, [_decision("a")])
    store.register_rules(["risky-transactions"], NOW - timedelta(days=100))
    store.register_rules(["statements", "social-networks"], NOW - timedelta(days=10))

    report = _render(store)

    assert "**Remove rule** `risky-transactions`" in report
    assert "`statements`" not in report.split("## Rule matches")[0]
    assert "`social-networks`" not in report.split("## Rule matches")[0]


def test_rescues_propose_reviewing_the_rule(tmp_path) -> None:
    store = _store(tmp_path, [_decision("a", subject="Ticket for 901365392888")])
    store.record_audits([AuditRow("a", "rescued", True, NOW, NOW)])

    report = _render(store)

    assert (
        "Rescues (false positives): 1 (100.0% of archived/trashed; target 0)" in report
    )
    assert "**Review rule** `social-networks`: caused 1 rescue(s)" in report
    assert "Ticket for ••2888" in report


def test_review_heavy_senders_and_unsubscribe_candidates(tmp_path) -> None:
    decisions = [
        _decision(
            f"u{i}",
            source=DecisionSource.UNCERTAIN,
            category="promotion",
            action=Action.KEEP,
            sender="x@new.example",
        )
        for i in range(3)
    ] + [
        _decision(
            f"p{i}",
            category="promotion",
            rule_name="gmail-promotions-with-unsubscribe",
            sender="deals@shop.example",
            unsubscribe=True,
        )
        for i in range(5)
    ]
    store = _store(tmp_path, decisions)

    report = _render(store)

    assert "**Add rule** for `new.example`: 3 messages needed review" in report
    assert "**Unsubscribe** from `shop.example`: 5 trashed" in report
    assert "Review rate: 37.5%" in report


def test_dry_run_only_window_warns(tmp_path) -> None:
    store = _store(tmp_path, [_decision("a")], applied=False)

    report = _render(store)

    assert "No applied runs in this window" in report
    assert "dry-run only: 1" in report


def test_messages_outside_window_are_excluded(tmp_path) -> None:
    store = _store(tmp_path, [_decision("a")], run_at=NOW - timedelta(days=120))

    report = _render(store)

    assert "Messages triaged: 0" in report
