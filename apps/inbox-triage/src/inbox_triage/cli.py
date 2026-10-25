from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import yaml
from gmail_core import GmailClient

from inbox_triage.audit import run_audit
from inbox_triage.brief import write_brief
from inbox_triage.classifier import Classifier, ClassifierError, SystemOneClassifier
from inbox_triage.config import TriageConfig, build_query
from inbox_triage.digest import write_digest
from inbox_triage.report import ReportSettings, write_report
from inbox_triage.rules import RuleConfigError
from inbox_triage.store import DecisionStore
from inbox_triage.triage import run_triage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Triage the Gmail inbox locally with rules and a localhost classifier"
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=["run", "audit", "report"],
        help=(
            "run: triage the inbox (default). audit: detect rescued/noise messages "
            "from what you did in Gmail (run daily). report: write a scorecard "
            "with rule proposals to the digest directory."
        ),
    )
    parser.add_argument(
        "--since-days",
        type=int,
        default=90,
        help="report: window in days (default 90, a quarter)",
    )
    parser.add_argument(
        "--min-rule-age-days",
        type=int,
        default=60,
        help="report: only propose removing rules active at least this long",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Archive/trash messages in Gmail (default is a dry run)",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max messages to read")
    parser.add_argument(
        "--config", type=Path, default=Path("config/triage.yaml"), help="Triage config"
    )
    parser.add_argument(
        "--credentials",
        type=Path,
        default=Path("secrets/credentials.json"),
        help="Path to Google OAuth client credentials",
    )
    parser.add_argument(
        "--token",
        type=Path,
        default=Path("secrets/token.json"),
        help="Path to the local OAuth token",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Private local state (decision log)",
    )
    parser.add_argument(
        "--digest-dir",
        type=Path,
        default=Path("digests"),
        help="Where the Markdown digest is written",
    )
    parser.add_argument(
        "--no-classifier",
        action="store_true",
        help="Use rules only; unmatched messages are left in the inbox",
    )
    parser.add_argument(
        "--print-query",
        action="store_true",
        help="Print the Gmail search query and exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.config.exists():
        raise SystemExit(f"Missing config file: {args.config}")
    try:
        config = TriageConfig.from_file(args.config)
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        problem = getattr(error, "problem", None) or "invalid YAML"
        raise SystemExit(
            f"Invalid YAML in {args.config}{where}: {problem}. "
            "Check indentation and that each line has a single 'key: value'."
        ) from None
    except (RuleConfigError, ValueError) as error:
        raise SystemExit(f"Invalid config {args.config}: {error}") from error

    query = build_query(config.query, config.processed_label)
    if args.print_query:
        print(query)
        return 0

    now = datetime.now().astimezone()
    if args.command == "report":
        store = DecisionStore(args.data_dir / "triage.sqlite")
        path = write_report(
            store,
            config.policy,
            args.digest_dir,
            now,
            ReportSettings(
                since_days=args.since_days, min_rule_age_days=args.min_rule_age_days
            ),
        )
        print(f"Report: {path}")
        return 0
    if args.command == "audit":
        store = DecisionStore(args.data_dir / "triage.sqlite")
        summary = run_audit(GmailClient(args.credentials, args.token), store, now)
        print(f"Audited: {summary.checked}")
        print(f"Outcomes: {dict(summary.outcomes)}")
        if summary.errors:
            print(f"Gmail errors: {summary.errors}", file=sys.stderr)
        return 1 if summary.errors else 0

    classifier: Classifier | None = None
    if config.classifier.enabled and not args.no_classifier:
        try:
            classifier = SystemOneClassifier(
                config.classifier.base_url,
                config.policy.classifier_categories(),
                model=config.classifier.model,
                api_key=os.environ.get(config.classifier.api_key_env),
                timeout=config.classifier.timeout_seconds,
            )
        except ClassifierError as error:
            raise SystemExit(str(error)) from error

    gmail = GmailClient(args.credentials, args.token)
    store = DecisionStore(args.data_dir / "triage.sqlite")
    store.register_rules((rule.name for rule in config.policy.rules), now)
    report = run_triage(
        gmail,
        config.policy,
        classifier,
        query=query,
        processed_label=config.processed_label,
        apply=args.apply,
        limit=args.limit or config.query.max_messages,
        already_handled=store.handled_message_ids(),
        started_at=now,
    )
    store.record(
        report.run_id,
        report.started_at.isoformat(),
        report.mode,
        report.decisions,
        report.applied_ids,
        report.errors,
    )
    awareness_categories = frozenset(
        name
        for name, category in config.policy.categories.items()
        if category.awareness
    )
    digest_path = write_digest(report, args.digest_dir, awareness_categories)
    brief_categories = tuple(
        name for name, category in config.policy.categories.items() if category.brief
    )
    brief_path = write_brief(report, args.digest_dir, brief_categories)

    # Counts only on stdout: message content stays in the digest and local log.
    actions = Counter(d.action.value for d in report.decisions)
    sources = Counter(d.source.value for d in report.decisions)
    print(f"Mode: {report.mode}")
    print(f"Triaged: {len(report.decisions)}")
    print(f"Actions: {dict(actions)}")
    print(f"Decided by: {dict(sources)}")
    if report.skipped_already_handled:
        print(f"Skipped (already handled): {report.skipped_already_handled}")
    if report.more_remaining:
        print(
            f"Stopped at the {report.limit}-message cap; more messages remain",
            file=sys.stderr,
        )
    if report.classifier_error:
        print(f"Classifier: {report.classifier_error}", file=sys.stderr)
    if report.errors:
        print(f"Gmail errors: {len(report.errors)}", file=sys.stderr)
    print(f"Digest: {digest_path}")
    print(f"Brief: {brief_path}")
    return 1 if report.errors else 0
