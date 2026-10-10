# mail-automation

Local-only Gmail automation. Mail is read through the Gmail API on this machine
and never sent to a cloud AI service.

| Member | Purpose |
|---|---|
| `packages/gmail-core` | Shared Gmail client, OAuth, message text extraction |
| `apps/moneywiz-export` | Bank transaction emails to MoneyWiz CSV |

## Setup

```bash
uv sync --all-packages
mkdir -p secrets config
# Put your Google OAuth client at secrets/credentials.json
cp apps/moneywiz-export/config/accounts.example.yaml config/accounts.yaml
uv run gmail-moneywiz-export          # dry run, from the repo root
```

See `apps/moneywiz-export/README.md` for exporter details.
