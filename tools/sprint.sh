#!/usr/bin/env bash
# sprint.sh — one ticket, one command, ticket in to test run commissioned.
#
#     ./tools/sprint.sh QA-642                  the whole thing
#     ./tools/sprint.sh QA-642 --testmo-only    phases 4-8 on a run folder that exists
#     ./tools/sprint.sh QA-642 --no-watch       stop after publishing to Linear
#     ./tools/sprint.sh QA-642 --push           create the cases over the API, no browser stop
#     ./tools/sprint.sh QA-642 --dry-run        stop short of creating anything in Testmo
#     ./tools/sprint.sh QA-642 --interval 300   poll every 5 minutes instead of 2
#
# Eight phases, one process:
#   1. draft      — claude runs /sprint: fetch, summarize, coverage, decide, draft, proof
#   2. publish    — the cases go to Linear as sub-issues, awaiting review
#   3. review     — poll Linear; a case that comes back with comments triggers /rework,
#                   which revises and republishes. Exits when every case is final.
#   4. export     — the approved cases become a Testmo import CSV
#   5. import     — the cases go into the repository. --push uses the bulk case API;
#                   without it, the CSV is imported in the browser and the script waits.
#   6. adopt      — refresh the cache, match the imported cases to their new ids
#   7. plan       — build the run manifest: milestone, configs, every case id
#   8. commission — create the milestone and the run(s)
#
# Phases 3 and 5 wait on a human, so this stays up for as long as review takes. Ctrl-C is
# safe at any point: the run folder holds the state and `--testmo-only` resumes the back
# half. Everything created outside the run folder is recorded in runs/<TICKET>/CLEANUP.md.
set -euo pipefail

TICKET="${1:-}"
if [[ -z "$TICKET" ]]; then
  echo "usage: ./tools/sprint.sh <TICKET-ID> [--testmo-only] [--push] [--no-watch] [--dry-run]" >&2
  echo "                         [--interval N] [--max-cycles N]" >&2
  exit 1
fi
shift
cd "$(dirname "$0")/.."

WATCH=1; INTERVAL=120; MAX_CYCLES=5; TESTMO_ONLY=0; DRY=0; PUSH=0; PASS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-watch)    WATCH=0; shift ;;
    --testmo-only) TESTMO_ONLY=1; shift ;;
    --dry-run)     DRY=1; shift ;;
    --push)        PUSH=1; shift ;;
    --interval)    INTERVAL="$2"; shift 2 ;;
    --max-cycles)  MAX_CYCLES="$2"; shift 2 ;;
    *)             PASS+=("$1"); shift ;;
  esac
done

# `claude` often lives on a PATH set in ~/.zshrc, which the bash running this script
# never reads. Look where it actually installs; CLAUDE_BIN overrides.
find_claude() {
  if [[ -n "${CLAUDE_BIN:-}" ]]; then echo "$CLAUDE_BIN"; return 0; fi
  if command -v claude >/dev/null 2>&1; then command -v claude; return 0; fi
  local c
  for c in "$HOME/.claude/local/claude" \
           "$HOME/.local/bin/claude" \
           "/opt/homebrew/bin/claude" \
           "/usr/local/bin/claude" \
           "$HOME/.bun/bin/claude" \
           "$HOME/.npm-global/bin/claude"; do
    [[ -x "$c" ]] && { echo "$c"; return 0; }
  done
  # Last resort: ask the login shell, which is where the PATH was set.
  c="$(zsh -lic 'command -v claude' 2>/dev/null | tail -1 || true)"
  [[ -n "$c" && -x "$c" ]] && { echo "$c"; return 0; }
  return 1
}

if [[ "$TESTMO_ONLY" -eq 0 ]]; then
  if [[ -d "runs/$TICKET" ]]; then
    echo "runs/$TICKET already exists." >&2
    echo "To carry an approved run on into Testmo:" >&2
    echo "  ./tools/sprint.sh $TICKET --testmo-only" >&2
    echo "To resume the review loop alone:" >&2
    echo "  python3 tools/review_sync.py watch $TICKET --interval $INTERVAL \\" >&2
    echo "      --on-rework \"claude -p '/rework $TICKET'\"" >&2
    exit 1
  fi

  if ! CLAUDE="$(find_claude)"; then
    echo "Could not find the 'claude' executable." >&2
    echo "Run 'which claude' in your normal shell, then either:" >&2
    echo "  export CLAUDE_BIN=/path/to/claude     (and re-run)" >&2
    echo "  or add its directory to PATH in ~/.bashrc as well as ~/.zshrc" >&2
    exit 1
  fi

  echo "=== 1-2. $TICKET — drafting and publishing ==="
  echo "    using $CLAUDE"
  EXTRA=""
  if [[ ${#PASS[@]} -gt 0 ]]; then EXTRA="${PASS[*]}"; fi
  "$CLAUDE" -p "/sprint $TICKET $EXTRA" --permission-mode acceptEdits

  if [[ "$WATCH" -eq 0 ]]; then
    echo "=== published; not watching (--no-watch) ==="
    exit 0
  fi

  echo
  echo "=== 3. $TICKET — waiting for review ==="
  echo "Approve a case by moving it to Product Review or Done."
  echo "Send one back by leaving a comment on it."
  echo
  python3 tools/review_sync.py watch "$TICKET" \
      --interval "$INTERVAL" \
      --max-cycles "$MAX_CYCLES" \
      --on-rework "$CLAUDE -p '/rework $TICKET' --permission-mode acceptEdits"
else
  if [[ ! -d "runs/$TICKET" ]]; then
    echo "no runs/$TICKET/ — nothing to carry into Testmo." >&2
    exit 1
  fi
  echo "=== $TICKET — Testmo phases only (4-8) ==="
fi

echo
echo "=== 4. $TICKET — building the Testmo import file ==="
python3 tools/case_export.py build "$TICKET"

echo
echo "=== 5. $TICKET — putting the cases in the repository ==="
if [[ "$PUSH" -eq 1 ]]; then
  if [[ "$DRY" -eq 1 ]]; then
    python3 tools/case_export.py push "$TICKET" --dry-run
  else
    python3 tools/case_export.py push "$TICKET"
  fi
else
  echo "Browser import (pass --push to use the API instead):"
  echo "  Testmo > Mobile App > the repository > Import"
  echo "  file: runs/$TICKET/08-import.csv   (map the columns by name)"
  echo
  if [[ ! -t 0 ]]; then
    echo "Not a terminal, so stopping here. After importing, resume with:"
    echo "  ./tools/sprint.sh $TICKET --testmo-only"
    exit 0
  fi
  read -r -p "Press enter once the import is done (ctrl-c to stop here): " _
fi

echo
echo "=== 6. $TICKET — refreshing the cache and adopting the new case ids ==="
python3 tools/case_export.py sync "$TICKET"

echo
echo "=== 7. $TICKET — planning the run ==="
python3 tools/testmo_run.py plan "$TICKET"

echo
echo "=== 8. $TICKET — commissioning ==="
if [[ "$DRY" -eq 1 ]]; then
  python3 tools/testmo_run.py commission "$TICKET" --dry-run
  echo
  echo "--dry-run: nothing was created in Testmo."
  exit 0
fi
python3 tools/testmo_run.py commission "$TICKET"

echo
echo "=== done. Everything created is listed in runs/$TICKET/CLEANUP.md ==="
python3 tools/ledger.py "$TICKET"
