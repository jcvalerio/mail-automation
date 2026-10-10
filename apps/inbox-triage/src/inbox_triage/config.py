from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from inbox_triage.models import Action, Priority
from inbox_triage.policy import CategoryPolicy, Policy
from inbox_triage.rules import Rule, RuleConfigError

DEFAULT_PROCESSED_LABEL = "Triage/Processed"


@dataclass(frozen=True)
class QueryConfig:
    only_unread: bool = True
    exclude_labels: tuple[str, ...] = ()
    extra: str = ""
    max_messages: int = 200


@dataclass(frozen=True)
class ClassifierConfig:
    enabled: bool = True
    base_url: str = "http://127.0.0.1:8765"
    model: str = "von-latest"
    api_key_env: str = "VON_API_KEY"
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class TriageConfig:
    query: QueryConfig
    classifier: ClassifierConfig
    policy: Policy
    processed_label: str

    @classmethod
    def from_file(cls, path: Path) -> TriageConfig:
        with path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TriageConfig:
        query_data = data.get("query") or {}
        classifier_data = data.get("classifier") or {}
        categories = _parse_categories(data.get("categories") or {})
        rules = [Rule.from_dict(rule) for rule in data.get("rules") or []]
        for rule in rules:
            if rule.category not in categories:
                raise RuleConfigError(
                    f"Rule '{rule.name}' uses undefined category '{rule.category}'"
                )
        policy = Policy(
            categories=categories,
            rules=rules,
            min_confidence=float(classifier_data.get("min_confidence", 0.85)),
            needs_action_threshold=float(
                classifier_data.get("needs_action_threshold", 0.7)
            ),
        )
        return cls(
            query=QueryConfig(
                only_unread=bool(query_data.get("only_unread", True)),
                exclude_labels=tuple(query_data.get("exclude_labels") or ()),
                extra=str(query_data.get("extra") or "").strip(),
                max_messages=int(query_data.get("max_messages", 200)),
            ),
            classifier=ClassifierConfig(
                enabled=bool(classifier_data.get("enabled", True)),
                base_url=str(
                    classifier_data.get("base_url") or ClassifierConfig.base_url
                ),
                model=str(classifier_data.get("model") or ClassifierConfig.model),
                api_key_env=str(
                    classifier_data.get("api_key_env") or ClassifierConfig.api_key_env
                ),
                timeout_seconds=float(classifier_data.get("timeout_seconds", 30.0)),
            ),
            policy=policy,
            processed_label=str(data.get("processed_label") or DEFAULT_PROCESSED_LABEL),
        )


def build_query(config: QueryConfig, processed_label: str) -> str:
    """Always scoped to the inbox; config can only narrow the search further."""
    parts = ["in:inbox"]
    if config.only_unread:
        parts.append("is:unread")
    for label in (*config.exclude_labels, processed_label):
        parts.append(f"-label:{label_search_term(label)}")
    if config.extra:
        parts.append(f"({config.extra})")
    return " ".join(parts)


def label_search_term(label_name: str) -> str:
    return label_name.strip().casefold().replace("/", "-").replace(" ", "-")


def _parse_categories(data: dict[str, Any]) -> dict[str, CategoryPolicy]:
    if not data:
        raise RuleConfigError("Config needs at least one category")
    categories: dict[str, CategoryPolicy] = {}
    for name, value in data.items():
        value = value or {}
        description = str(value.get("description") or "").strip()
        if not description:
            raise RuleConfigError(f"Category '{name}' needs a description")
        categories[str(name)] = CategoryPolicy(
            description=description,
            action=Action(value.get("action", Action.KEEP)),
            priority=Priority(value.get("priority", Priority.NORMAL)),
            human_only=bool(value.get("human_only", False)),
            awareness=bool(value.get("awareness", False)),
        )
    return categories
