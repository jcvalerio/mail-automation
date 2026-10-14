#!/usr/bin/env bash
# Morning mail run, scheduled by launchd (see scripts/install-launchd.sh).
#
#   1. inbox-triage audit         record what you did with yesterday's decisions
#                                 (before you empty Trash, so nothing is "gone")
#   2. inbox-triage --apply       triage the inbox, write digests/YYYY-MM-DD.md
#   3. inbox-triage report        on the review cadence (weekly, monthly, quarterly)
#
# gmail-moneywiz-export is not part of it: it asks interactively to resolve
# categories, so run it by hand. Bank emails stay in the inbox until then
# (triage skips its labels via query.exclude_labels).
#
# Everything runs locally. Von is started on loopback if it isn't already
# running, and stopped again afterwards. Output goes to data/logs/ (private).
#
# Env:
#   TRIAGE_FIRST_APPLY   YYYY-MM-DD of the first --apply; drives the report cadence
#   MORNING_DRY_RUN=1    run triage without --apply

set -u

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO" || exit 1

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
export GMAIL_NONINTERACTIVE=1
# Gmail is the only remote host; the classifier must never go through a proxy.
export NO_PROXY="127.0.0.1,localhost"

VON_URL="http://127.0.0.1:8765"
LOG_DIR="$REPO/data/logs"
mkdir -p "$LOG_DIR"
find "$LOG_DIR" -name 'morning-*.log' -mtime +60 -delete
LOG="$LOG_DIR/morning-$(date +%Y-%m-%d).log"
exec >>"$LOG" 2>&1 </dev/null

failures=()
log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }

step() {
  local name="$1"
  shift
  log "== $name"
  if "$@"; then
    log "-- $name ok"
  else
    log "-- $name FAILED ($?)"
    failures+=("$name")
  fi
}

von_up() {
  curl -s --noproxy '*' -m 2 -o /dev/null "$VON_URL/health"
}

apply_flag="--apply"
[ "${MORNING_DRY_RUN:-0}" = "1" ] && apply_flag=""

log "morning run start (repo $REPO)"

if ! VON_API_KEY="$(security find-generic-password -s von-api-key -w 2>/dev/null)"; then
  log "Von API key not found in Keychain (service von-api-key)"
  failures+=("keychain")
fi
export VON_API_KEY

von_pid=""
if ! von_up; then
  log "starting Von"
  HF_HUB_OFFLINE=1 VON_CORS_ORIGINS=http://127.0.0.1 \
    von serve --host 127.0.0.1 --port 8765 --device mps &
  von_pid=$!
  for _ in $(seq 1 60); do
    von_up && break
    sleep 2
  done
  von_up || log "Von did not start; triage will keep unclassified mail in the inbox"
fi

step audit uv run inbox-triage audit
triage_out="$(uv run inbox-triage $apply_flag </dev/null)"
triage_rc=$?
printf '%s\n' "$triage_out"
[ $triage_rc -eq 0 ] || failures+=("triage")

# Review cadence: weekly (Mondays) for the first month after the first apply,
# then monthly (1st), then quarterly (1st of Jan/Apr/Jul/Oct).
if [ -n "${TRIAGE_FIRST_APPLY:-}" ]; then
  start=$(date -j -f %Y-%m-%d "$TRIAGE_FIRST_APPLY" +%s 2>/dev/null || echo "")
  if [ -n "$start" ]; then
    age_days=$(( ($(date +%s) - start) / 86400 ))
    weekday=$(date +%u)
    day=$(date +%d)
    month=$(date +%m)
    window=""
    if [ "$age_days" -le 31 ]; then
      [ "$weekday" = "1" ] && window=7
    elif [ "$age_days" -le 120 ]; then
      [ "$day" = "01" ] && window=31
    elif [ "$day" = "01" ]; then
      case "$month" in 01 | 04 | 07 | 10) window=92 ;; esac
    fi
    [ -n "$window" ] && step report uv run inbox-triage report --since-days "$window"
  fi
fi

if [ -n "$von_pid" ]; then
  kill "$von_pid" 2>/dev/null
  wait "$von_pid" 2>/dev/null
fi

# Counts only: the notification never shows senders or subjects.
summary="$(printf '%s\n' "$triage_out" | grep -E '^Actions:' | head -1)"
if [ ${#failures[@]} -gt 0 ]; then
  message="Failed: ${failures[*]}. Log: data/logs/$(basename "$LOG")"
else
  message="${summary:-Done}. Run /digest in Claude Code."
fi
osascript -e "display notification \"${message//\"/}\" with title \"Mail triage\"" || true

log "morning run end (failures: ${#failures[@]})"
[ ${#failures[@]} -eq 0 ]
