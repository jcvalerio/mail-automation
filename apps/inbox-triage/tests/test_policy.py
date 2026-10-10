from inbox_triage.models import Action, Classification, DecisionSource, Priority
from tests.helpers import example_config, make_message


def test_starred_messages_are_always_kept() -> None:
    policy = example_config().policy
    message = make_message(
        label_ids=("INBOX", "STARRED", "CATEGORY_PROMOTIONS"),
        list_unsubscribe="<mailto:u@shop.example>",
    )

    decision = policy.decide_by_guard_or_rule(message)

    assert decision.action is Action.KEEP
    assert decision.source is DecisionSource.GUARD


def test_rule_uses_category_defaults() -> None:
    policy = example_config().policy
    message = make_message(
        label_ids=("INBOX", "CATEGORY_PROMOTIONS"),
        list_unsubscribe="<mailto:u@shop.example>",
    )

    decision = policy.decide_by_guard_or_rule(message)

    assert decision.category == "promotion"
    assert decision.action is Action.TRASH
    assert decision.rule_name == "gmail-promotions-with-unsubscribe"


def test_confident_model_result_uses_category_action() -> None:
    policy = example_config().policy

    decision = policy.decide_by_model(
        make_message(), Classification("newsletter", 0.93, 0.1)
    )

    assert decision.action is Action.ARCHIVE
    assert decision.source is DecisionSource.MODEL


def test_low_confidence_keeps_message_for_review() -> None:
    policy = example_config().policy

    decision = policy.decide_by_model(
        make_message(), Classification("promotion", 0.6, 0.1)
    )

    assert decision.action is Action.KEEP
    assert decision.source is DecisionSource.UNCERTAIN


def test_needs_action_overrides_trash_category() -> None:
    policy = example_config().policy

    decision = policy.decide_by_model(
        make_message(), Classification("promotion", 0.99, 0.9)
    )

    assert decision.action is Action.KEEP
    assert decision.priority is Priority.HIGH
