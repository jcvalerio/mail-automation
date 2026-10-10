from __future__ import annotations

from dataclasses import dataclass, replace

from inbox_triage.models import (
    Action,
    Classification,
    Decision,
    DecisionSource,
    InboxMessage,
    Priority,
)
from inbox_triage.rules import Rule, first_matching_rule


@dataclass(frozen=True)
class CategoryPolicy:
    description: str
    action: Action
    priority: Priority
    # Only a real person can be in this category; automated senders are
    # re-assigned to their best non-human category.
    human_only: bool = False
    # List these in the digest's "For awareness" section even when handled.
    awareness: bool = False


@dataclass(frozen=True)
class Policy:
    categories: dict[str, CategoryPolicy]
    rules: list[Rule]
    min_confidence: float
    needs_action_threshold: float

    def category(self, name: str) -> CategoryPolicy:
        try:
            return self.categories[name]
        except KeyError as error:
            raise KeyError(f"Category '{name}' is not defined in policy") from error

    def decide_by_guard_or_rule(self, message: InboxMessage) -> Decision | None:
        if message.is_starred:
            return Decision(
                message=message,
                category="starred",
                action=Action.KEEP,
                priority=Priority.HIGH,
                source=DecisionSource.GUARD,
                reason="Starred messages are never touched",
            )
        rule = first_matching_rule(self.rules, message)
        if rule is None:
            return None
        category = self.category(rule.category)
        return Decision(
            message=message,
            category=rule.category,
            action=rule.action or category.action,
            priority=rule.priority or category.priority,
            source=DecisionSource.RULE,
            reason=f"Matched rule '{rule.name}'",
            rule_name=rule.name,
        )

    def decide_by_model(
        self, message: InboxMessage, classification: Classification
    ) -> Decision:
        classification = self._exclude_human_only(message, classification)
        needs_action = classification.needs_action_probability
        if needs_action is not None and needs_action >= self.needs_action_threshold:
            return Decision(
                message=message,
                category=classification.category,
                action=Action.KEEP,
                priority=Priority.HIGH,
                source=DecisionSource.MODEL,
                reason="Model says this likely needs your action",
                confidence=classification.category_confidence,
                needs_action_probability=needs_action,
            )
        if classification.category_confidence < self.min_confidence:
            return Decision(
                message=message,
                category=classification.category,
                action=Action.KEEP,
                priority=Priority.NORMAL,
                source=DecisionSource.UNCERTAIN,
                reason=(
                    f"Model confidence {classification.category_confidence:.2f} "
                    f"is below {self.min_confidence:.2f}"
                ),
                confidence=classification.category_confidence,
                needs_action_probability=needs_action,
            )
        category = self.category(classification.category)
        return Decision(
            message=message,
            category=classification.category,
            action=category.action,
            priority=category.priority,
            source=DecisionSource.MODEL,
            reason="Model classification",
            confidence=classification.category_confidence,
            needs_action_probability=needs_action,
        )

    def _exclude_human_only(
        self, message: InboxMessage, classification: Classification
    ) -> Classification:
        category = self.categories.get(classification.category)
        if not (category and category.human_only and message.is_automated_sender):
            return classification
        alternatives = {
            name: probability
            for name, probability in classification.probabilities.items()
            if name in self.categories and not self.categories[name].human_only
        }
        if not alternatives:
            # Nothing else to fall back to: force the uncertain path.
            return replace(classification, category_confidence=0.0)
        best = max(alternatives, key=alternatives.__getitem__)
        # Raw (not renormalized) probability keeps the confidence gate honest.
        return replace(
            classification, category=best, category_confidence=alternatives[best]
        )

    def unclassified(self, message: InboxMessage, reason: str) -> Decision:
        return Decision(
            message=message,
            category="unclassified",
            action=Action.KEEP,
            priority=Priority.NORMAL,
            source=DecisionSource.UNCLASSIFIED,
            reason=reason,
        )
