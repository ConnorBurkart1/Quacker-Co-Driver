#!/usr/bin/env bash
# sprint.sh — one ticket, one command, all the way through review.
#
#     ./tools/sprint.sh QA-642                 draft, publish, then watch until approved
#     ./tools/sprint.sh QA-642 --no-watch      stop after publishing
#     ./tools/sprint.sh QA-642 --interval 300  poll every 5 minutes instead of 2
#
# Three phases, one process:
#   1. draft   — claude runs /sprint: fetch, summarize, coverage, decide, draft, proof
#   2. publish — /sprint ends by publishing the cases to Linear as sub-issues
#   3. review  — watch polls Linear; when a case comes back with comments, it calls
#                /rework, which revises and republishes, then keeps watching.
#                Exits when every case is final.
#
# Phase 3 waits on a human, so this command stays up for as long as the review takes.
# That is the point: ctrl-c is safe at any time and the run folder keeps the state, so
# re-running `watch` picks up exactly where it left off.
set -euo pipefail

TICKET="${1:-}"
if [[ -z "$TICKET" ]]; then
  echo "usage: ./tools/sprint.sh <TICKET-ID> [--no-watch] [--interval N] [--max-cycles N]" >&2
  exit 1
fi
shift
cd "$(dirname "$0")/.."

WATCH=1; INTERVAL=120; MAX_CYCLES=5; PASS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-watch)   WATCH=0; shift ;;
    --interval)   INTERVAL="$2"; shift 2 ;;
    --max-cycles) MAX_CYCLES="$2"; shift 2 ;;
    *)            PASS+=("$1"); shift ;;
  esac
done

if [[ -d "runs/$TICKET" ]]; then
  echo "runs/$TICKET already exists." >&2
  echo "Delete it to start over, or run the review loop alone:" >&2
  echo "  python3 tools/review_sync.py watch $TICKET --interval $INTERVAL \\" >&2
  echo "      --on-rework \"claude -p '/rework $TICKET'\"" >&2
  exit 1
fi

echo "=== $TICKET — drafting and publishing ==="
EXTRA=""
if [[ ${#PASS[@]} -gt 0 ]]; then EXTRA="${PASS[*]}"; fi
claude -p "/sprint $TICKET $EXTRA" --permission-mode acceptEdits

if [[ "$WATCH" -eq 0 ]]; then
  echo "=== published; not watching (--no-watch) ==="
  exit 0
fi

echo
echo "=== $TICKET — watching for review ==="
echo "Move a case to Product Review or Done to approve it."
echo "Move it to In Progress WITH a comment to send it back for rework."
echo "Ctrl-C is safe; re-run this script's watch line to resume."
echo
exec python3 tools/review_sync.py watch "$TICKET" \
    --interval "$INTERVAL" \
    --max-cycles "$MAX_CYCLES" \
    --on-rework "claude -p '/rework $TICKET' --permission-mode acceptEdits"
