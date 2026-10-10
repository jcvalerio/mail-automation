"""Local SQLite decision log. Lives under data/, which agents must not read."""

from __future__ import annotations

import sqlite3
from contextlib import closing
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
"""


class DecisionStore:
    def __init__(self, path: Path):
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.executescript(SCHEMA)

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
            )
            for d in decisions
        ]
        with closing(self._connect()) as connection, connection:
            connection.executemany(
                "INSERT OR REPLACE INTO decisions VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)
