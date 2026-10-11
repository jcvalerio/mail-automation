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


def test_old_database_is_migrated_in_place(tmp_path) -> None:
    import sqlite3

    path = tmp_path / "old.sqlite"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE decisions (
            run_id TEXT NOT NULL, run_at TEXT NOT NULL, mode TEXT NOT NULL,
            message_id TEXT NOT NULL, thread_id TEXT NOT NULL,
            sender_email TEXT NOT NULL, sender_domain TEXT NOT NULL,
            subject TEXT NOT NULL, gmail_category TEXT NOT NULL,
            category TEXT NOT NULL, action TEXT NOT NULL, priority TEXT NOT NULL,
            source TEXT NOT NULL, rule_name TEXT, confidence REAL,
            needs_action_probability REAL, applied INTEGER NOT NULL, error TEXT,
            PRIMARY KEY (run_id, message_id)
        );
        INSERT INTO decisions VALUES ('r0', '2026-10-10T07:00:00-06:00', 'apply',
            'old', 't', 'a@x.example', 'x.example', 's', 'primary', 'newsletter',
            'archive', 'low', 'rule', 'r', NULL, NULL, 1, NULL);
        """
    )
    connection.commit()
    connection.close()

    store = DecisionStore(path)
    store.record(
        "run1", "2026-10-11T07:00:00-06:00", "apply", [_decision("new")], {"new"}, {}
    )

    rows = {row.message_id: row for row in store.decisions()}
    assert rows["old"].has_list_unsubscribe is False
    assert rows["new"].applied is True
    assert store.handled_message_ids() == {"old", "new"}
