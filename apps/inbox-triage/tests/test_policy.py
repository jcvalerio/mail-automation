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


def test_automated_sender_cannot_be_personal() -> None:
    policy = example_config().policy
    message = make_message(sender="LinkedIn <messages-noreply@linkedin.example>")

    decision = policy.decide_by_model(
        message,
        Classification(
            "personal",
            0.91,
            0.2,
            probabilities={"personal": 0.91, "newsletter": 0.06, "promotion": 0.03},
        ),
    )

    assert decision.category == "newsletter"
    assert decision.confidence == 0.06
    assert decision.source is DecisionSource.UNCERTAIN
    assert decision.action is Action.KEEP


def test_unsubscribe_header_marks_sender_as_automated() -> None:
    policy = example_config().policy
    message = make_message(
        sender="Ana <ana@shop.example>", list_unsubscribe="<mailto:u@shop.example>"
    )

    decision = policy.decide_by_model(
        message,
        Classification(
            "personal", 0.9, 0.1, probabilities={"personal": 0.04, "promotion": 0.95}
        ),
    )

    assert decision.category == "promotion"
    assert decision.action is Action.TRASH


def test_human_sender_can_be_personal() -> None:
    policy = example_config().policy

    decision = policy.decide_by_model(
        make_message(sender="Ana <ana@mail.example>"),
        Classification("personal", 0.9, 0.2, probabilities={"personal": 0.9}),
    )

    assert decision.category == "personal"
    assert decision.priority is Priority.HIGH


def test_needs_action_with_unsure_category_gets_no_category_labels() -> None:
    policy = example_config().policy

    unsure = policy.decide_by_model(
        make_message(sender="Calendar <calendar-notification@google.example>"),
        Classification(
            "risky_transaction", 0.09, 0.8, probabilities={"risky_transaction": 0.09}
        ),
    )
    sure = policy.decide_by_model(
        make_message(sender="Bank <alerta@bank.example>"),
        Classification(
            "risky_transaction", 0.95, 0.8, probabilities={"risky_transaction": 0.95}
        ),
    )

    assert unsure.action is Action.KEEP and unsure.labels == ()
    assert sure.action is Action.KEEP and sure.labels == ("Triage/Awareness",)
