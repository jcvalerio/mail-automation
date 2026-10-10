# AGENTS.md

Scope: repository-wide instructions for AI coding agents.
Package-specific rules live in each member's own `AGENTS.md` and also apply.

## Workspace layout
- `uv` workspace, Python 3.12+.
- `packages/gmail-core/`: shared Gmail API client, OAuth, message text extraction.
- `apps/moneywiz-export/`: bank transaction emails to MoneyWiz CSV (see its `AGENTS.md`).
- Runtime files live at the repo root and are gitignored: `secrets/`, `config/*.yaml`, `exports/`, `data/`.
- Run app CLIs from the repo root so they pick up root `secrets/` and `config/`.

## Dev environment
- Sync: `uv sync --all-packages`.
- Run: `uv run gmail-moneywiz-export` (from the repo root).

## Checks to run
- Lint: `uv run ruff check .`.
- Format check: `uv run ruff format --check .`.
- Tests: run per member from its directory, e.g.
  `uv run --directory packages/gmail-core pytest` and
  `uv run --directory apps/moneywiz-export pytest`.

## Privacy and safety
- This project exists to keep mail away from cloud AI services. Do not add
  integrations that send message content to any remote API other than Gmail.
- Agents must never read `secrets/`, `config/*.yaml`, `exports/`, or `data/`;
  only the generated digest is meant for AI consumption.
- Never commit raw emails, names, card IDs, OAuth tokens, or real transactions.
- Dry-run is the default; ask before changing Gmail mutation behavior.
