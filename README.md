# mail-automation

Local-only Gmail automation. Mail is read through the Gmail API on this machine
and never sent to a cloud AI service.

| Member | Purpose |
|---|---|
| `packages/gmail-core` | Shared Gmail client, OAuth, message text extraction |
| `apps/moneywiz-export` | Bank transaction emails to MoneyWiz CSV |
| `apps/inbox-triage` | Inbox keep/archive/trash with rules + a localhost classifier, daily digest |

## Setup

```bash
uv sync --all-packages
mkdir -p secrets config
# Put your Google OAuth client at secrets/credentials.json
cp apps/moneywiz-export/config/accounts.example.yaml config/accounts.yaml
uv run gmail-moneywiz-export          # dry run, from the repo root
```

See `apps/moneywiz-export/README.md` and `apps/inbox-triage/README.md` for details.

## Daily schedule (launchd)

`scripts/morning.sh` runs, in order: `inbox-triage audit`, `inbox-triage --apply`, and
`inbox-triage report --since-days N` on the review cadence (Mondays with a 7-day window
for the first month after the first apply, then the 1st of each month with 31 days, then
the 1st of Jan/Apr/Jul/Oct with 92 days). It starts
Von on loopback if it isn't running and stops it afterwards, then shows a macOS
notification with counts only. Logs go to `data/logs/` (private).

If `MORNING_IMESSAGE_TO` is set, it also sends you the phone brief by iMessage:
what needs your attention (sender and subject) and, for categories marked
`brief: true` such as school, the subject plus Gmail's preview so you can see
what to do. Archived and trashed mail is counts only. On a failed run the
message starts with what failed. It is sent through the Messages app, end-to-end
encrypted, to your own number or Apple ID; nothing else leaves the Mac besides
Gmail calls. A failed send never fails the run (the notification says so).

`gmail-moneywiz-export` is not scheduled because it prompts to resolve categories; run
it by hand. Until you do, bank emails stay in the inbox (triage excludes their labels).

```bash
scripts/install-launchd.sh 2026-10-11        # date of your first --apply; daily at 07:00
MORNING_IMESSAGE_TO=+15555550123 scripts/install-launchd.sh 2026-10-11   # plus the phone brief
launchctl kickstart gui/$(id -u)/dev.mail-automation.morning   # run once now
scripts/install-launchd.sh --uninstall
MORNING_DRY_RUN=1 scripts/morning.sh         # manual dry run of the whole sequence
MORNING_DRY_RUN=1 MORNING_IMESSAGE_TO=+15555550123 scripts/morning.sh   # same, and send the brief
uv run inbox-triage report --since-days 7    # report on demand, from the repo root
```

The first send asks macOS to let the script control Messages; run the line above
from Terminal once to allow it before relying on the 07:00 run. Messages must be
signed in to iMessage on the Mac, and the Mac must be awake (launchd runs the
job on wake if it slept through 07:00).

Scheduled runs set `GMAIL_NONINTERACTIVE=1`, so an expired Gmail token fails the
run (see the notification) instead of waiting for a browser login. Run any CLI once
by hand to sign in again. If your Google Cloud OAuth app is in "Testing" status,
Google expires its refresh tokens after 7 days; publish it to "In production"
(no verification is needed for personal use) to avoid weekly sign-ins.

In Claude Code, `/digest` summarizes the newest digest and proposes rule changes
(`/digest report` for the latest report). It reads only `digests/` and
`config/triage.yaml`.
