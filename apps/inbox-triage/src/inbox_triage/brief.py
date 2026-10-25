"""Plain-text phone brief: what needs you today, short enough to read on a phone.

scripts/morning.sh sends it to the user's own iMessage (end-to-end encrypted),
so it carries less than the digest: kept messages that need attention and kept
messages in `brief: true` categories (with Gmail's preview, for what to do).
Archived and trashed mail appears only as counts. Text gets the digest's
sanitizing and number masking.
"""

from __future__ import annotations

import html
from collections import Counter
from email.utils import parseaddr
from pathlib import Path

from inbox_triage.digest import attention_sort_key, sanitize
from inbox_triage.models import Action, Decision, DecisionSource, Priority
from inbox_triage.triage import RunReport

MAX_ITEMS = 8
PREVIEW_CHARS = 160


def render_brief(report: RunReport, brief_categories: tuple[str, ...] = ()) -> str:
    decisions = report.decisions
    kept = [d for d in decisions if d.action is Action.KEEP]
    actions = Counter(d.action.value for d in decisions)
    counts = ", ".join(f"{key} {value}" for key, value in actions.most_common())
    header = f"Mail {report.started_at:%a %d %b}: {len(decisions)} triaged"
    if counts:
        header += f" ({counts})"
    if not report.apply:
        header += ", dry run"
    lines = [header]
    if report.classifier_error:
        lines.append("⚠️ Classifier unavailable: unclassified mail stayed in the inbox")
    if report.errors:
        lines.append(f"⚠️ Gmail errors: {len(report.errors)}")
    if report.more_remaining:
        lines.append("⚠️ Hit the message cap; more mail is waiting")

    attention = sorted(
        (
            d
            for d in kept
            if d.priority is Priority.HIGH and d.category not in brief_categories
        ),
        key=attention_sort_key,
    )
    sections: list[tuple[str, list[str]]] = []
    if attention:
        sections.append(
            (f"Needs you ({len(attention)})", _items(attention, _attention_line))
        )
    for category in brief_categories:
        group = [d for d in kept if d.category == category]
        if group:
            title = category.replace("_", " ").capitalize()
            sections.append((f"{title} ({len(group)})", _items(group, _preview_line)))

    for title, items in sections:
        lines += ["", title, *items]
    if not sections:
        lines += ["", "Nothing needs you today."]

    review = [
        d
        for d in kept
        if d.priority is not Priority.HIGH
        and d.category not in brief_categories
        and d.source in {DecisionSource.UNCERTAIN, DecisionSource.UNCLASSIFIED}
    ]
    if review:
        lines += ["", f"Review on the Mac: {len(review)} unsure (/digest)"]
    return "\n".join(lines) + "\n"


def write_brief(
    report: RunReport, digest_dir: Path, brief_categories: tuple[str, ...] = ()
) -> Path:
    digest_dir.mkdir(parents=True, exist_ok=True)
    suffix = "" if report.apply else "-dry-run"
    path = digest_dir / f"brief-{report.started_at:%Y-%m-%d}{suffix}.txt"
    path.write_text(render_brief(report, brief_categories), encoding="utf-8")
    return path


def _items(decisions: list[Decision], render) -> list[str]:
    lines = [render(d) for d in decisions[:MAX_ITEMS]]
    if len(decisions) > MAX_ITEMS:
        lines.append(f"+{len(decisions) - MAX_ITEMS} more in /digest")
    return lines


def _sender_name(decision: Decision) -> str:
    name, _ = parseaddr(decision.message.sender)
    return sanitize(name or decision.message.sender_email, 40)


def _attention_line(decision: Decision) -> str:
    return f"• {_sender_name(decision)}: {sanitize(decision.message.subject, 90)}"


def _preview_line(decision: Decision) -> str:
    line = f"• {sanitize(decision.message.subject, 90)}"
    # Gmail returns snippets HTML-escaped (&#39;, &amp;).
    preview = html.unescape(decision.message.snippet)
    if preview.strip():
        line += f"\n  {sanitize(preview, PREVIEW_CHARS)}"
    return line
