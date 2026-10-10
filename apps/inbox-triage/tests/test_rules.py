import pytest

from inbox_triage.rules import Rule, RuleConfigError, first_matching_rule
from tests.helpers import make_message


def test_rule_requires_all_conditions() -> None:
    rule = Rule.from_dict(
        {
            "name": "gh-sec",
            "category": "github_security",
            "match": {
                "sender_domains": ["github.com"],
                "subject_regex": "dependabot|security",
            },
        }
    )

    assert rule.matches(
        make_message(
            sender="GitHub <notifications@github.com>",
            subject="[me/repo] Dependabot alert",
        )
    )
    assert not rule.matches(
        make_message(sender="GitHub <notifications@github.com>", subject="New issue")
    )
    assert not rule.matches(
        make_message(sender="x@evil.example", subject="security dependabot")
    )


def test_sender_domain_matches_subdomains_but_not_lookalikes() -> None:
    rule = Rule.from_dict(
        {"name": "r", "category": "c", "match": {"sender_domains": ["github.com"]}}
    )

    assert rule.matches(make_message(sender="a@noreply.github.com"))
    assert not rule.matches(make_message(sender="a@notgithub.com"))
    assert not rule.matches(make_message(sender="a@github.com.evil.example"))


def test_gmail_category_and_unsubscribe_conditions() -> None:
    rule = Rule.from_dict(
        {
            "name": "promos",
            "category": "promotion",
            "match": {"gmail_categories": ["promotions"], "has_list_unsubscribe": True},
        }
    )

    promo = make_message(
        label_ids=("INBOX", "CATEGORY_PROMOTIONS"),
        list_unsubscribe="<mailto:u@shop.example>",
    )
    promo_without_unsubscribe = make_message(label_ids=("INBOX", "CATEGORY_PROMOTIONS"))
    assert rule.matches(promo)
    assert not rule.matches(promo_without_unsubscribe)


def test_subject_contains_is_case_insensitive() -> None:
    rule = Rule.from_dict(
        {
            "name": "r",
            "category": "c",
            "match": {"subject_contains": ["Nuevo inicio de sesión"]},
        }
    )

    assert rule.matches(make_message(subject="Alerta: NUEVO INICIO DE SESIÓN"))


def test_first_matching_rule_wins() -> None:
    rules = [
        Rule.from_dict(
            {"name": "a", "category": "x", "match": {"subject_contains": "hi"}}
        ),
        Rule.from_dict(
            {"name": "b", "category": "y", "match": {"subject_contains": "hi"}}
        ),
    ]

    assert first_matching_rule(rules, make_message(subject="hi")).name == "a"
    assert first_matching_rule(rules, make_message(subject="bye")) is None


@pytest.mark.parametrize(
    "data",
    [
        {"category": "c", "match": {"subject_contains": "x"}},
        {"name": "r", "match": {"subject_contains": "x"}},
        {"name": "r", "category": "c", "match": {}},
        {"name": "r", "category": "c", "match": {"body_contains": "x"}},
    ],
)
def test_invalid_rules_are_rejected(data) -> None:
    with pytest.raises(RuleConfigError):
        Rule.from_dict(data)


def test_example_rules_cover_spanish_security_and_risky_notices() -> None:
    from tests.helpers import example_config

    policy = example_config().policy
    cases = {
        "Notificación de Inicio de Sesión en la Aplicación FLEX": "security_alert",
        "Tu sesión se inició con éxito": "security_alert",
        "Un nuevo dispositivo está usando tu cuenta": "security_alert",
        "Creación de retiro sin tarjeta": "risky_transaction",
        "Liberty Factura electrónica N° 123": "receipt",
    }
    for subject, category in cases.items():
        decision = policy.decide_by_guard_or_rule(make_message(subject=subject))
        assert decision is not None and decision.category == category, subject


def test_social_messages_and_mentions_are_kept_rest_is_newsletter() -> None:
    from tests.helpers import example_config

    policy = example_config().policy
    cases = [
        ("noreply@discord.com", "saoudrizwan mentioned you in Cline", "direct_message"),
        (
            "notifications-noreply@linkedin.com",
            "Ana mentioned you in a comment",
            "direct_message",
        ),
        (
            "messages-noreply@linkedin.com",
            "Ana sent you a new message",
            "direct_message",
        ),
        (
            "messaging-digest-noreply@linkedin.com",
            "Ana is waiting for your reply",
            "direct_message",
        ),
        (
            "notifications-noreply@linkedin.com",
            "Ana te mencionó en un comentario",
            "direct_message",
        ),
        (
            "notifications-noreply@linkedin.com",
            "You have 3 new invitations",
            "newsletter",
        ),
        (
            "messages-noreply@linkedin.com",
            "Juan, you're popular - 28 profile viewers",
            "newsletter",
        ),
        (
            "jobs-noreply@linkedin.com",
            "Engineering Manager at Example Corp",
            "newsletter",
        ),
    ]
    for sender, subject, category in cases:
        decision = policy.decide_by_guard_or_rule(
            make_message(sender=sender, subject=subject)
        )
        assert decision is not None and decision.category == category, subject
