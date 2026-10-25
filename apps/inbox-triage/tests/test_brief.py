from datetime import datetime

from inbox_triage.brief import MAX_ITEMS, render_brief, write_brief
from inbox_triage.models import Classification
from inbox_triage.rules import Rule
from inbox_triage.triage import run_triage
from tests.helpers import FakeClassifier, FakeMailbox, example_config, make_metadata


def _report(messages, classification, *, apply=True, classifier=True):
    config = example_config()
    config.policy.rules.insert(
        0, Rule(name="school", category="school", sender_domains=("school.example",))
    )
    return run_triage(
        FakeMailbox(messages),
        config.policy,
        FakeClassifier(classification) if classifier else None,
        query="in:inbox",
        processed_label=config.processed_label,
        apply=apply,
        limit=None,
        already_handled=set(),
        started_at=datetime(2026, 10, 24, 7, 0),
    )


def test_example_config_marks_school_for_the_brief() -> None:
    assert example_config().policy.categories["school"].brief


def test_brief_lists_attention_and_school_preview_only() -> None:
    report = _report(
        [
            make_metadata(
                "a",
                sender="Ana Mora <ana@friend.example>",
                subject="Can you sign the lease?",
                snippet="Should not appear",
            ),
            make_metadata(
                "s",
                sender="Escuela <info@school.example>",
                subject="Field trip on Friday",
                snippet="Please sign the permission slip &amp; pay 5000 by Thursday",
            ),
        ],
        Classification("personal", 0.95, 0.9),
    )

    brief = render_brief(report, ("school",))

    assert brief.startswith("Mail Sat 24 Oct: 2 triaged (keep 2)\n")
    assert "Needs you (1)\n• Ana Mora: Can you sign the lease?" in brief
    assert "Should not appear" not in brief
    assert (
        "School (1)\n• Field trip on Friday\n"
        "  Please sign the permission slip & pay 5000 by Thursday"
    ) in brief


def test_brief_never_lists_archived_or_trashed_mail() -> None:
    report = _report(
        [
            make_metadata(
                "p",
                sender="Shop <deals@shop.example>",
                subject="Secret sale",
                list_unsubscribe="<mailto:u@shop.example>",
                label_ids=("INBOX", "CATEGORY_PROMOTIONS"),
            )
        ],
        Classification("promotion", 0.99, 0.01),
    )

    brief = render_brief(report, ("school",))

    assert "Secret sale" not in brief
    assert "shop.example" not in brief
    assert "Nothing needs you today." in brief


def test_brief_masks_numbers_and_flags_problems() -> None:
    report = _report(
        [
            make_metadata(
                "u",
                sender="someone@unknown.example",
                subject="Invoice 123456789",
            )
        ],
        Classification("personal", 0.95, 0.9),
        apply=False,
        classifier=False,
    )

    brief = render_brief(report)

    assert ", dry run" in brief.splitlines()[0]
    assert "Classifier unavailable" in brief
    assert "123456789" not in brief
    assert "Review on the Mac: 1 unsure" in brief


def test_brief_caps_long_sections(tmp_path) -> None:
    report = _report(
        [
            make_metadata(f"s{i}", sender="info@school.example", subject=f"Notice {i}")
            for i in range(MAX_ITEMS + 2)
        ],
        Classification("personal", 0.95, 0.1),
    )

    path = write_brief(report, tmp_path, ("school",))

    assert path.name == "brief-2026-10-24.txt"
    assert "+2 more in /digest" in path.read_text(encoding="utf-8")
