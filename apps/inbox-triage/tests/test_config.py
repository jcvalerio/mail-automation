import pytest

from inbox_triage.config import TriageConfig, build_query, label_search_term
from inbox_triage.rules import RuleConfigError
from tests.helpers import example_config


def test_example_config_loads() -> None:
    config = example_config()

    assert "promotion" in config.policy.categories
    assert config.classifier.base_url.startswith("http://127.0.0.1")


def test_query_is_always_inbox_scoped() -> None:
    config = example_config()

    query = build_query(config.query, config.processed_label)

    assert query.startswith("in:inbox is:unread ")
    assert "-label:banks-bac" in query
    assert "-label:triage-processed" in query


def test_extra_terms_are_grouped_and_anded() -> None:
    config = TriageConfig.from_dict(
        {
            "query": {"only_unread": False, "extra": "newer_than:7d OR in:sent"},
            "categories": {"other": {"description": "Anything"}},
        }
    )

    query = build_query(config.query, config.processed_label)

    assert query == "in:inbox -label:triage-processed (newer_than:7d OR in:sent)"


def test_label_search_term_matches_gmail_syntax() -> None:
    assert label_search_term("Triage/Processed") == "triage-processed"
    assert label_search_term("My Label") == "my-label"


def test_rule_with_undefined_category_is_rejected() -> None:
    with pytest.raises(RuleConfigError, match="undefined category"):
        TriageConfig.from_dict(
            {
                "categories": {"other": {"description": "Anything"}},
                "rules": [
                    {
                        "name": "r",
                        "category": "nope",
                        "match": {"subject_contains": "x"},
                    }
                ],
            }
        )


def test_rule_only_categories_are_not_classifier_choices() -> None:
    policy = example_config().policy

    choices = policy.classifier_categories()

    assert "fyi" in policy.categories
    assert "fyi" not in choices
    assert "promotion" in choices


def test_config_needs_a_classifier_category() -> None:
    with pytest.raises(RuleConfigError, match="classifier"):
        TriageConfig.from_dict(
            {"categories": {"fyi": {"description": "x", "rule_only": True}}}
        )
