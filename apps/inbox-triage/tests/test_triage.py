from datetime import datetime

from inbox_triage.classifier import ClassifierError
from inbox_triage.models import Action, Classification, DecisionSource
from inbox_triage.triage import run_triage
from tests.helpers import FakeClassifier, FakeMailbox, example_config, make_metadata

PROMO = make_metadata(
    "promo",
    label_ids=("INBOX", "UNREAD", "CATEGORY_PROMOTIONS"),
    list_unsubscribe="<mailto:u@shop.example>",
)
NEWSLETTER = make_metadata("news", sender="News <hi@news.example>")
NOT_IN_INBOX = make_metadata("sent", label_ids=("SENT",))


def _run(mailbox, classifier, *, apply, already_handled=frozenset()):
    config = example_config()
    return run_triage(
        mailbox,
        config.policy,
        classifier,
        query="in:inbox",
        processed_label=config.processed_label,
        apply=apply,
        limit=None,
        already_handled=set(already_handled),
        started_at=datetime(2026, 10, 10, 7, 0),
    )


def test_dry_run_makes_no_gmail_changes() -> None:
    mailbox = FakeMailbox([PROMO, NEWSLETTER])
    classifier = FakeClassifier(Classification("newsletter", 0.95, 0.1))

    report = _run(mailbox, classifier, apply=False)

    assert [d.action for d in report.decisions] == [Action.TRASH, Action.ARCHIVE]
    assert mailbox.modified == []
    assert mailbox.trashed == []
    assert mailbox.labels_created == []
    assert report.applied_ids == set()


def test_rules_short_circuit_the_classifier() -> None:
    mailbox = FakeMailbox([PROMO, NEWSLETTER])
    classifier = FakeClassifier(Classification("newsletter", 0.95, 0.1))

    _run(mailbox, classifier, apply=False)

    assert classifier.calls == ["news"]


def test_apply_archives_with_label_and_trashes() -> None:
    mailbox = FakeMailbox([PROMO, NEWSLETTER])
    classifier = FakeClassifier(Classification("newsletter", 0.95, 0.1))

    report = _run(mailbox, classifier, apply=True)

    assert mailbox.trashed == ["promo"]
    assert mailbox.modified == [("news", ["Label_processed"], ["INBOX"])]
    assert report.applied_ids == {"promo", "news"}


def test_messages_outside_inbox_are_never_touched() -> None:
    mailbox = FakeMailbox([NOT_IN_INBOX])
    classifier = FakeClassifier(Classification("promotion", 0.99, 0.0))

    report = _run(mailbox, classifier, apply=True)

    assert report.decisions == []
    assert report.skipped_not_in_inbox == 1
    assert mailbox.trashed == []


def test_classifier_failure_fails_closed_and_stops_calling() -> None:
    second = make_metadata("news2", sender="b@news.example")
    mailbox = FakeMailbox([NEWSLETTER, second])
    classifier = FakeClassifier(ClassifierError("connection refused"))

    report = _run(mailbox, classifier, apply=True)

    assert classifier.calls == ["news"]
    assert {d.source for d in report.decisions} == {DecisionSource.UNCLASSIFIED}
    assert all(d.action is Action.KEEP for d in report.decisions)
    assert report.classifier_error == "connection refused"
    assert mailbox.modified == [] and mailbox.trashed == []


def test_apply_skips_messages_handled_in_earlier_runs() -> None:
    mailbox = FakeMailbox([NEWSLETTER])
    classifier = FakeClassifier(Classification("other", 0.95, 0.1))

    report = _run(mailbox, classifier, apply=True, already_handled={"news"})

    assert report.decisions == []
    assert report.skipped_already_handled == 1


def test_gmail_errors_are_recorded_per_message() -> None:
    mailbox = FakeMailbox([PROMO, NEWSLETTER])
    mailbox.fail_ids = {"promo"}
    classifier = FakeClassifier(Classification("newsletter", 0.95, 0.1))

    report = _run(mailbox, classifier, apply=True)

    assert report.errors == {"promo": "boom"}
    assert report.applied_ids == {"news"}
