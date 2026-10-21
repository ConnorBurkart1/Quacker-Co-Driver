# Quacker / Co-Driver

A QA loop for the Eleos mobile app: a Linear ticket goes in, the right test coverage comes
out, gets reviewed, and — eventually — gets run and reported back to Testmo.

The point is not automation for its own sake. It is that **nothing ships without an
inspection of the area that changed** — and that the mechanical parts of producing that
inspection (reading the ticket, finding what already covers it, drafting what doesn't exist,
proofing it) stop costing a person their afternoon.

## One command

```bash
./tools/sprint.sh QA-642
```

Three phases, one process:

1. **Draft** — fetch the ticket from Linear, fill the summary, check coverage, decide,
   draft, proof.
2. **Publish** — each case becomes a sub-issue under the ticket's "Create a test case
   outline" child, labelled by platform, in `In QA`.
3. **Review** — poll Linear. A new comment on a case queues it for rework; `/rework`
   revises the cases and republishes. Exits when every case is final.

Phase 3 waits on a human, so the command stays up for as long as the review takes. Ctrl-C
is safe — the run folder holds the state, and `review_sync.py stage <TICKET>` says where to
pick it back up.

Inside a Claude Code session, `/sprint QA-642` does the same thing.

## Reviewing, in Linear

The review surface is Linear itself, not a bespoke UI. Comments are the instruction; status
is the verdict.

| Do this | And | Result |
|---|---|---|
| Leave a **new comment** on a case | any status | queued for rework |
| Move to **Done** or **Product Review** | — | final; never touched again |
| Move to **In Progress** / **In Review** with no new comment | — | reported as "no instruction", nothing guessed |
| Move to **Canceled** | — | the case is dropped |

**The run folder is canonical for case text; Linear is canonical for status and comments.**
Never edit case text in Linear — the next publish overwrites it. Renames *are* handled:
change the title in `02-cases.md` and the issue is renamed in place.

## Layout

```
tools/            five scripts — the facts
.claude/skills/   judgment: ticket-scrape, coverage-check, case-draft
.claude/agents/   case-proofer — independent review in a fresh context
.claude/commands/ /sprint and /rework
docs/             thesis, rollout plan, prompts, Linear setup, handoff
runs/             one folder per ticket (git-ignored)
CLAUDE.md         the operating rules — read it before changing how the loop behaves
.mcp.json         Linear reads, read-only endpoint
```

`tools/` is deterministic and auditable. `.claude/` is where the decisions live. The split
is deliberate — a number should never depend on which model answered.

## The run folder is the state

```
00-candidates.md   areas scored from the ticket text — evidence, not an answer
01-summary.md      the ticket, plus the Structured block drafting reads
02-cases.md        the cases, in house format            <- canonical
03-coverage.md     what already exists
04-decision.md     what to run, what to add, what is broken
05-proof.md        what the proofer found and what was rejected
06-rework.md       generated; exists only when something needs revising
07-questions.md    what the run is blocked on, and who owns each answer
review-state.json  case <-> Linear issue, and the comment watermark
```

A correction made in `01-summary.md` propagates to everything downstream. Fix it there, not
in a conversation.

## The tools

| Script | Job |
|---|---|
| `tools/refresh.py` | Pull the live Testmo repository and build the local cache |
| `tools/coverage.py` | Every query — `areas`, `area`, `search`, `case`, `suggest`, `health` |
| `tools/new_run.py` | Start a run folder; `--linear` fetches the ticket over the API |
| `tools/validate_cases.py` | Mechanical checks on drafted cases before a human reads them |
| `tools/review_sync.py` | `publish`, `poll`, `watch`, `status`, `stage` — the Linear review loop |

```bash
python3 tools/coverage.py areas pin
python3 tools/coverage.py search "Send Diagnostics"     # search before claiming a gap
python3 tools/review_sync.py stage QA-642               # where did this run stall?
```

The commands are shortcuts, not the ceiling. The cache is normalized JSON — for a question
that doesn't fit a command, write a few lines of Python against it.

## Setup

```bash
cp .env.example .env          # TESTMO_TOKEN, TESTMO_URL, LINEAR_API_KEY
python3 tools/refresh.py      # pulls the live repository, ~40s
```

`.env` is git-ignored and is what the Python tools read. **`.mcp.json` is the exception:**
it expands `${LINEAR_API_KEY}` from the *shell* environment at server load, so for MCP the
key also has to be exported (`~/.bashrc` on the VM, `~/.zshrc` on the Mac). Two mechanisms,
both correct. `.mcp.json` holds no secret and is committed.

On the VM, outbound traffic goes through an allowlisting proxy — a blocked request returns
**HTTP 418**, which means it never left the machine. Three lines are needed:

```
GET  https://eleostechnologies.testmo.net/api/v1/*
POST https://mcp.linear.app/mcp/readonly
POST https://api.linear.app/graphql
```

## Access — what is enforced where

- **Testmo** is REST with a `GET`-only allowlist line. There is no read-only token tier, so
  **that line is the entire enforcement.** `refresh.py` issues GET only. Never add a write
  method.
- **Linear reads** go through `https://mcp.linear.app/mcp/readonly`, which exposes no write
  tool at all.
- **Linear writes** happen only in `tools/review_sync.py`, over GraphQL, creating and
  updating sub-issues of one named parent. This is deliberate: a model holding `issueCreate`
  can write anything anywhere, whereas a script does a fixed set of operations you can diff.
  **Don't move writes into MCP to save a step.**
- The key is scoped to `Read`/`Write` on the **QA team only**. Product work (GRP, DRI, BUG,
  EIN) is out of reach by design; those tickets use the paste fallback.

## Where this is

**Picking this up cold? Read `CLAUDE.md`, then `docs/HANDOFF.md`.**

| Stage | State |
|---|---|
| A — the coverage answer | **Done** |
| B — ticket in, cases out | **Done** |
| C — read-only access | **Done** — verified 2026-10-21 |
| D — the review view | **Done differently** — Linear is the review surface, so no bespoke UI |
| E — the device leg | Not started. Runs on the Mac, where the phones are |
| F — the evidence view | Not started. Needs E |
| G — reporting out | Not started. Testmo results and the Linear sub-issue |

QA-642 ran the whole loop end to end on 2026-10-21 — ticket to five published cases,
reviewed in Linear, reworked from comments, approved. See
`docs/Claude-Sprint-Workflow-Rollout.md` for the staging and
`docs/Claude-Sprint-Workflow-Thesis.md` for what the remaining stages need.

**Known gap:** the `--on-rework` hook has run only with a human watching. The polling,
comment detection, rename and republish are all proven; firing `/rework` unattended is not.

## Two things that have gone wrong, so they don't again

**Never claim something is uncovered from `coverage.py area` alone.** `area` answers "what
is filed here", not "what tests this". Anything used as a *tool* by other features has its
coverage filed under its consumers — Send Diagnostics is in Settings **and** in Scanning and
Dashboard. Search by the control's **shipped** name first; the ticket's name for it is often
not the product's.

**Proofing has caught a material error on every run**, both times in the direction that
produced less work — one claimed a gap that didn't exist, one claimed coverage that wasn't
there. A clean proof is suspicious, not reassuring.

## The rule that governs all of it

**The floor is always a scoped pass on the area that changed** — whether the ticket adds a
feature, upgrades a dependency, or refactors something meant to behave identically. "No new
functionality" means no new *cases*. It never means skip the area.
