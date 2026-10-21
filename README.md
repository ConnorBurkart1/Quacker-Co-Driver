# Dispatch / Co-Driver

A QA loop for the Eleos mobile app: a Linear ticket goes in, the right test coverage comes
out, gets run, and gets reported back to Testmo.

The point is not automation for its own sake. It is that **nothing ships without an
inspection of the area that changed** — and that the mechanical parts of producing that
inspection (reading the ticket, finding what already covers it, drafting what doesn't exist,
proofing it) stop costing a person their afternoon.

## Layout

```
tools/      the four scripts — the facts
.claude/    skills and agents — the judgment
docs/       the thesis, the rollout plan, the prompts
runs/       one folder per ticket (git-ignored)
```

`tools/` is deterministic and auditable: fetch, normalize, count. `.claude/` is where the
decisions live. The split is deliberate — a number should never depend on which model
answered.

## Setup

```bash
cp .env.example .env          # then fill in your Testmo token
python3 tools/refresh.py      # pulls the live repository, ~40s
```

`refresh.py` issues **GET only**, and the proxy allowlist carries no write method.
Don't add one.

## The tools

| Script | Job |
|---|---|
| `tools/refresh.py` | Pull the live Testmo repository and build the local cache |
| `tools/coverage.py` | Every query — `areas`, `area`, `search`, `case`, `suggest`, `health` |
| `tools/new_run.py` | Start a run folder for a ticket and score candidate areas |
| `tools/validate_cases.py` | Mechanical checks on drafted cases before a human reads them |

```bash
python3 tools/coverage.py areas pin
python3 tools/coverage.py area "Pin" --full
python3 tools/coverage.py search "rescan request"
```

The commands are shortcuts, not the ceiling. The cache is normalized JSON — for a question
that doesn't fit a command, write a few lines of Python against it.

## The skills

These load automatically when Claude Code runs with this repo as the working directory.
You ask a question; the skill fires. There are no commands to memorize.

| | What it answers |
|---|---|
| `coverage-check` | "What covers this area, is it still valid, what's missing?" |
| `case-draft` | Ticket → decision → cases in house format |
| `case-proofer` *(agent)* | Independent review, fresh context, no knowledge of how the cases were produced |

## Where this is

Built and working: the coverage answer, and ticket-to-cases. Testmo access is live,
read-only. Linear access, the device leg and reporting back out are still ahead — see
`docs/Claude-Sprint-Workflow-Rollout.md` for the staging, and
`docs/Claude-Sprint-Workflow-Thesis.md` for what's feasible and what it needs.

## The rule that governs all of it

**The floor is always a scoped pass on the area that changed** — whether the ticket adds a
feature, upgrades a dependency, or refactors something meant to behave identically. "No new
functionality" means no new *cases*. It never means skip the area.
