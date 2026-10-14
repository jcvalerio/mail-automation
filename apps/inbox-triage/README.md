# inbox-triage

Local-only Gmail inbox triage. It reads **headers and Gmail's short snippet only**
(never message bodies) for inbox messages, decides keep / archive / trash, and
writes a Markdown digest. Nothing is sent anywhere except Gmail and a
classifier running on `localhost`.

## How a message is decided

1. **Guard:** starred messages and anything without the `INBOX` label are never touched.
2. **Rules** (`config/triage.yaml`): first match wins. Sender, domain, subject,
   Gmail tab, `List-Unsubscribe`, `List-Id`.
3. **Classifier:** a local System One decision model answers two typed questions:
   which category, and does this need your action.
   - Probability of "needs action" ≥ `needs_action_threshold`: keep, high priority.
   - Category probability < `min_confidence`: keep, listed for review.
   - Otherwise: the category's configured action.
   - Categories marked `human_only` (e.g. `personal`) can't be assigned to
     automated senders (noreply/alerts addresses or an unsubscribe header);
     the next-best category is used with its raw probability.
4. **Fail closed:** if the classifier is down or returns something invalid, the
   remaining messages stay in the inbox.

Archived messages get the `Triage/Processed` label. Categories can add their
own labels (e.g. `Triage/Awareness`, `Triage/School`), applied to kept,
archived, and trashed messages alike. Trash is Gmail's Trash (recoverable,
labels intact, for 30 days); permanent deletion is not implemented.

Rules can also match on age (`older_than_days`, `newer_than_days`), e.g. to
archive school mail once it is a month old.

## Outputs

| Path (repo root) | Contents | AI assistants may read |
|---|---|---|
| `digests/YYYY-MM-DD[-dry-run].md` | Summary, needs-attention list, counts by category and sender domain | Yes |
| `data/triage.sqlite` | Full decision log (subjects, senders, scores) | **No** (denied in `.claude/settings.json`) |

Digest text from emails is sanitized and truncated, and runs of 6 or more digits
(account, card, invoice numbers) are masked to their last 4. Archived and trashed
mail appears only as counts and sender domains, except categories marked
`awareness: true` (e.g. security notices, cardless withdrawals), which are
listed per platform with their distinct subjects.

## Setup

Run everything from the repo root.

```bash
cp apps/inbox-triage/config/triage.example.yaml config/triage.yaml
uv run inbox-triage --print-query            # check the Gmail search
uv run inbox-triage --no-classifier          # dry run with rules only
```

The OAuth token in `secrets/` is shared with `moneywiz-export`.

### Local classifier (Von)

[Von](https://github.com/wfzyx/von) is an Apache-2.0, 395M-parameter System One
model that serves a TypeSafe-compatible `/v1/systemone` API. Install it as an
isolated tool, not into this workspace:

```bash
uv tool install von-sdk==1.3.7

# One-time: create an API key and keep it in the macOS Keychain.
security add-generic-password -a "$USER" -s von-api-key -w "$(openssl rand -hex 24)"
```

Download the weights once (about 3.2 GB). This must happen **before** you start
the server with `HF_HUB_OFFLINE=1`; with an empty cache the server answers every
request with HTTP 422 "Failed to load Option-Marker decision weights".

```bash
$(uv tool dir)/von-sdk/bin/python -c "
from huggingface_hub import snapshot_download
print(snapshot_download('wfzyx/von', revision='main', allow_patterns=[
    'config.json', 'tokenizer.json', 'tokenizer_config.json', 'model.safetensors',
    'option_marker.pt', 'marker_calibration.json', 'calibration.json']))"
cat ~/.cache/huggingface/hub/models--wfzyx--von/refs/main   # record the revision
```

Then start it offline, bound to loopback only, with CORS locked down. Von's
defaults are `0.0.0.0` and `*`.

```bash
export VON_API_KEY="$(security find-generic-password -s von-api-key -w)"
HF_HUB_OFFLINE=1 VON_CORS_ORIGINS=http://127.0.0.1 \
  von serve --host 127.0.0.1 --port 8765 --device mps
```

The first request after startup takes a few seconds while the model loads;
after that expect roughly 200 ms per message on an M2.

Then, in another shell:

```bash
export VON_API_KEY="$(security find-generic-password -s von-api-key -w)"
uv run inbox-triage                          # dry run
uv run inbox-triage --apply                  # only after reviewing dry runs
```

Any other `/v1/systemone` server (Rizzo Flow, Kev, ollaya) works by changing
`classifier.base_url`. Non-localhost URLs are refused.

## Quality loop: audit and report

```bash
uv run inbox-triage audit      # daily, before `--apply` and before emptying Trash
uv run inbox-triage report     # quarterly (default window 90 days)
```

`audit` re-checks the current Gmail labels of messages handled in the last
25 days (before Trash empties at 30) and records what you did afterwards:

| Outcome | Meaning |
|---|---|
| `rescued` | Triage trashed or archived it, and you moved it back (false positive) |
| `noise` | Triage kept it, and you trashed or archived it while still unread |
| `confirmed` | You agreed (filed a kept message after reading, or trashed an archived one) |
| `ok` / `gone` | No change yet / Gmail no longer has it |

`report` writes `digests/report-YYYY-MM-DD.md`: scorecard (review rate,
rescues, noise), matches per rule and per category, new senders, awareness
trends, a random sample of trashed mail to skim, and proposals:

- **Remove rule:** no matches in the window and active for at least
  `--min-rule-age-days` (default 60).
- **Review rule/category:** caused rescues.
- **Add rule:** a sender needed review 3 or more times, or its kept mail was
  removed unread.
- **Unsubscribe:** a sender with an unsubscribe link had 5 or more messages
  trashed.

Suggested cadence: weekly for the first month after `--apply`, then monthly,
then quarterly once rescues stay at 0.

## Recommended rollout

1. Run dry runs for about a week and read `digests/*-dry-run.md`.
2. Turn recurring mistakes into rules.
3. Then use `--apply`.
