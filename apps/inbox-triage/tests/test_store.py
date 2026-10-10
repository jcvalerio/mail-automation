from inbox_triage.models import Action, Decision, DecisionSource, Priority
from inbox_triage.store import DecisionStore
from tests.helpers import make_message


def _decision(message_id: str) -> Decision:
    return Decision(
        message=make_message(message_id),
        category="newsletter",
        action=Action.ARCHIVE,
        priority=Priority.LOW,
        source=DecisionSource.MODEL,
        reason="test",
        confidence=0.9,
    )


def test_only_applied_decisions_count_as_handled(tmp_path) -> None:
    store = DecisionStore(tmp_path / "triage.sqlite")
    store.record("run1", "2026-10-10T07:00", "dry-run", [_decision("a")], set(), {})
    store.record(
        "run2",
        "2026-10-11T07:00",
        "apply",
        [_decision("b"), _decision("c")],
        {"b"},
        {"c": "boom"},
    )

    assert store.handled_message_ids() == {"b"}
