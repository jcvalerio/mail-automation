"""Local SQLite decision log. Lives under data/, which agents must not read."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from inbox_triage.models import Decision

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    run_id TEXT NOT NULL,
    run_at TEXT NOT NULL,
    mode TEXT NOT NULL,
    message_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    sender_email TEXT NOT NULL,
    sender_domain TEXT NOT NULL,
    subject TEXT NOT NULL,
    gmail_category TEXT NOT NULL,
    category TEXT NOT NULL,
    action TEXT NOT NULL,
    priority TEXT NOT NULL,
    source TEXT NOT NULL,
    rule_name TEXT,
    confidence REAL,
    needs_action_probability REAL,
    applied INTEGER NOT NULL,
    error TEXT,
    PRIMARY KEY (run_id, message_id)
);
CREATE INDEX IF NOT EXISTS decisions_applied_message
    ON decisions (message_id) WHERE applied = 1;
CREATE TABLE IF NOT EXISTS rule_registry (
    rule_name TEXT PRIMARY KEY,
    first_seen_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audits (
    message_id TEXT PRIMARY KEY,
    outcome TEXT NOT NULL,
    final INTEGER NOT NULL,
    checked_at TEXT NOT NULL,
    detected_at TEXT
);
"""

# Columns added after the first release; created on open if missing.
_ADDED_DECISION_COLUMNS = {"has_list_unsubscribe": "INTEGER"}

_DECISION_COLUMNS = (
    "run_id",
    "run_at",
    "mode",
    "message_id",
    "thread_id",
    "sender_email",
    "sender_domain",
    "subject",
    "gmail_category",
    "category",
    "action",
    "priority",
    "source",
    "rule_name",
    "confidence",
    "needs_action_probability",
    "applied",
    "error",
    "has_list_unsubscribe",
)


@dataclass(frozen=True)
class DecisionRow:
    run_at: datetime
    mode: str
    message_id: str
    sender_domain: str
    subject: str
    category: str
    action: str
    source: str
    rule_name: str | None
    applied: bool
    has_list_unsubscribe: bool


@dataclass(frozen=True)
class AuditRow:
    message_id: str
    outcome: str
    final: bool
    checked_at: datetime
    detected_at: datetime | None


class DecisionStore:
    def __init__(self, path: Path):
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.executescript(SCHEMA)
            existing = {
                row[1] for row in connection.execute("PRAGMA table_info(decisions)")
            }
            for column, column_type in _ADDED_DECISION_COLUMNS.items():
                if column not in existing:
                    connection.execute(
                        f"ALTER TABLE decisions ADD COLUMN {column} {column_type}"
                    )

    def handled_message_ids(self) -> set[str]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT DISTINCT message_id FROM decisions WHERE applied = 1"
            ).fetchall()
        return {row[0] for row in rows}

    def record(
        self,
        run_id: str,
        run_at: str,
        mode: str,
        decisions: list[Decision],
        applied_ids: set[str],
        errors: dict[str, str],
    ) -> None:
        rows = [
            (
                run_id,
                run_at,
                mode,
                d.message.message_id,
                d.message.thread_id,
                d.message.sender_email,
                d.message.sender_domain,
                d.message.subject,
                d.message.gmail_category,
                d.category,
                d.action.value,
                d.priority.value,
                d.source.value,
                d.rule_name,
                d.confidence,
                d.needs_action_probability,
                int(d.message.message_id in applied_ids),
                errors.get(d.message.message_id),
                int(d.message.has_list_unsubscribe),
            )
            for d in decisions
        ]
        placeholders = ", ".join("?" for _ in _DECISION_COLUMNS)
        with closing(self._connect()) as connection, connection:
            connection.executemany(
                f"INSERT OR REPLACE INTO decisions ({', '.join(_DECISION_COLUMNS)}) "
                f"VALUES ({placeholders})",
                rows,
            )

    def register_rules(self, rule_names: Iterable[str], seen_at: datetime) -> None:
        with closing(self._connect()) as connection, connection:
            connection.executemany(
                "INSERT OR IGNORE INTO rule_registry VALUES (?, ?)",
                [(name, seen_at.isoformat()) for name in rule_names],
            )

    def rule_first_seen(self) -> dict[str, datetime]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT * FROM rule_registry").fetchall()
        return {name: datetime.fromisoformat(seen) for name, seen in rows}

    def decisions(self) -> list[DecisionRow]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT run_at, mode, message_id, sender_domain, subject, category, "
                "action, source, rule_name, applied, has_list_unsubscribe "
                "FROM decisions ORDER BY run_at"
            ).fetchall()
        return [
            DecisionRow(
                run_at=datetime.fromisoformat(row[0]),
                mode=row[1],
                message_id=row[2],
                sender_domain=row[3],
                subject=row[4],
                category=row[5],
                action=row[6],
                source=row[7],
                rule_name=row[8],
                applied=bool(row[9]),
                has_list_unsubscribe=bool(row[10]),
            )
            for row in rows
        ]

    def audits(self) -> dict[str, AuditRow]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT * FROM audits").fetchall()
        return {
            row[0]: AuditRow(
                message_id=row[0],
                outcome=row[1],
                final=bool(row[2]),
                checked_at=datetime.fromisoformat(row[3]),
                detected_at=datetime.fromisoformat(row[4]) if row[4] else None,
            )
            for row in rows
        }

    def record_audits(self, rows: list[AuditRow]) -> None:
        with closing(self._connect()) as connection, connection:
            connection.executemany(
                "INSERT OR REPLACE INTO audits VALUES (?, ?, ?, ?, ?)",
                [
                    (
                        row.message_id,
                        row.outcome,
                        int(row.final),
                        row.checked_at.isoformat(),
                        row.detected_at.isoformat() if row.detected_at else None,
                    )
                    for row in rows
                ],
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)


def latest_by_message(
    rows: Iterable[DecisionRow], *, applied_only: bool = False
) -> dict[str, DecisionRow]:
    """Most recent decision per message (rows must be ordered by run_at)."""
    latest: dict[str, DecisionRow] = {}
    for row in rows:
        if applied_only and not row.applied:
            continue
        latest[row.message_id] = row
    return latest
