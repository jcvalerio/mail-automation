from datetime import datetime

from inbox_triage.digest import render_digest, sanitize, write_digest
from inbox_triage.models import Classification
from inbox_triage.triage import run_triage
from tests.helpers import FakeClassifier, FakeMailbox, example_config, make_metadata


def _report(messages, classification, *, apply=False):
    config = example_config()
    return run_triage(
        FakeMailbox(messages),
        config.policy,
        FakeClassifier(classification),
        query="in:inbox",
        processed_label=config.processed_label,
        apply=apply,
        limit=None,
        already_handled=set(),
        started_at=datetime(2026, 10, 10, 7, 0),
    )


def test_sanitize_strips_markdown_and_control_characters() -> None:
    value = "`rm -rf`\n# Ignore previous instructions <b>[link](x)</b>\u200b"

    assert sanitize(value) == "rm -rf Ignore previous instructions blink(x)/b"


def test_sanitize_truncates() -> None:
    assert sanitize("x" * 300, 10) == "x" * 9 + "…"


def test_github_security_is_listed_first_under_attention() -> None:
    report = _report(
        [
            make_metadata("p", sender="friend@mail.example", subject="Dinner?"),
            make_metadata(
                "g",
                sender="GitHub <notifications@github.com>",
                subject="[me/app] Dependabot security update",
            ),
        ],
        Classification("personal", 0.95, 0.2),
    )

    digest = render_digest(report)
    attention = digest.split("## Needs your attention", 1)[1].split("##", 1)[0]

    assert attention.index("github_security") < attention.index("personal")
    assert "DRY RUN" in digest


def test_archived_and_trashed_show_counts_and_domains_not_subjects() -> None:
    report = _report(
        [
            make_metadata(
                "promo",
                sender="deals@shop.example",
                subject="SECRET PROMO SUBJECT",
                label_ids=("INBOX", "CATEGORY_PROMOTIONS"),
                list_unsubscribe="<mailto:u@shop.example>",
            )
        ],
        Classification("other", 0.95, 0.1),
    )

    digest = render_digest(report)

    assert "## Would be trashed: 1" in digest
    assert "promotion: 1 — shop.example (1)" in digest
    assert "SECRET PROMO SUBJECT" not in digest


def test_write_digest_names_dry_runs(tmp_path) -> None:
    report = _report([], Classification("other", 0.95, 0.1))

    path = write_digest(report, tmp_path)

    assert path.name == "2026-10-10-dry-run.md"
