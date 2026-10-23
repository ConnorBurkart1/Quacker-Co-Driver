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

Nine phases, one process:

1. **Draft** — fetch the ticket from Linear, fill the summary, check coverage, decide,
   draft, proof.
2. **Publish** — each case becomes a sub-issue under the ticket's "Create a test case
   outline" child, labelled by platform, in `In QA`.
3. **Review** — poll Linear. A new comment on a case queues it for rework; `/rework`
   revises the cases and republishes. Exits when every case is final.
4. **Export** — the approved cases become a Testmo import CSV.
5. **Import** — the cases go into the repository. `--push` uses the bulk case API;
   without it, you import the CSV in the browser and the script waits.
6. **Adopt** — refresh the cache and match each imported case to its new Testmo id.
7. **Plan** — build the run manifest: milestone, configs, every case id in scope.
8. **Commission** — create the milestone, the test run(s), and the exploratory session.
9. **Link** — comment each Testmo artifact onto the Linear sub-issue it belongs to:
   cases on "Create test case outline", the run on "Test Run", the session on
   "Exploratory testing".

Useful flags:

```bash
./tools/sprint.sh QA-642 --push          # create the cases over the API, no browser stop
./tools/sprint.sh QA-642 --testmo-only   # phases 4-8 on a run folder that already exists
./tools/sprint.sh QA-642 --no-watch      # stop after publishing to Linear
./tools/sprint.sh QA-642 --dry-run       # stop short of creating anything in Testmo
./tools/sprint.sh QA-642 --progress 15   # heartbeat every 15s while drafting
```

Phases 1-2 are a single `claude -p` call that prints nothing until it finishes, so a
heartbeat reports which run-folder artifacts have landed:

```
    [01:20] 4/8 · wrote up what already covers this
    [01:40] 5/8 · decided the scoped pass and what to add
```

Phases 3 and 5 wait on a human, so the command stays up for as long as review takes.
Ctrl-C is safe — the run folder holds the state, `review_sync.py stage <TICKET>` says where
the review stalled, and `--testmo-only` resumes the back half. **Everything created outside
the run folder is recorded in `runs/<TICKET>/CLEANUP.md`**, so a run can always be undone.

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

**A case moved to Canceled is dropped** — `case_export.py` reads the review outcome and
refuses to import it. Review is the only human gate in the loop; a tool that imported a
canceled case anyway would silently override it.

**The run folder is canonical for case text; Linear is canonical for status and comments.**
Never edit case text in Linear — the next publish overwrites it. Renames *are* handled:
change the title in `02-cases.md` and the issue is renamed in place.

## What a case carries into Testmo

Two fields exist so a drafted case can always be told apart from a vetted one, and traced
back to why it was written.

**Status is `Claude - Needs Review`, never `In Use`.** `In Use` is what the team's 1,240
vetted cases carry. A case written minutes ago has not earned it, and once a case is in the
repository nothing in its text says who wrote it — the status is the only thing that does.
A QA lead promotes it by hand after watching it run on a device. **Nothing in this loop
promotes it**; a gate that approves itself is not a gate.

The consequence is intended: `coverage.py` counts these as *unrunnable*, not as coverage,
until they are promoted. An area holding nothing but unpromoted cases still reads as
uncovered — because in the sense that matters, it is. Unpromoted cases are not free to
leave sitting.

**Every case links back to the ticket that caused it.** Testmo's `Issues` field takes bare
tracker keys, comma-separated, and the ticket passed to `sprint.sh` goes in automatically.
A case can name more of its own with an `- **Issues:** EIN-6924` line; they merge after the
ticket. Pasting a full Linear URL works — the key is extracted.

| | Status | Issues |
|---|---|---|
| CSV import (default) | ✅ | ✅ comma-separated keys |
| `--push` (the API) | ✅ | ✅ `{display_id, integration_id: 2}` |

Approval in Linear and promotion in Testmo are **two different gates**. Linear means the
words are right. Testmo means the case actually runs.

## Testmo artifacts link back into Linear

Phase 9 writes each created artifact into the **description** of the sub-issue that owns
it, matching by title:

| Created in Testmo | Linked on the sub-issue |
|---|---|
| Test cases | "Create test case outline" |
| Test run | "Test Run" |
| Exploratory session | "Exploratory testing" |
| Milestone | "Create milestone …", when the ticket has one |

Everything from a `## Testmo` heading to the end of the description belongs to this tool;
**whatever sits above it is never touched** — QA-691 keeps its Google Doc link. Re-running
replaces that block rather than stacking copies, and an unchanged description is left
alone. The marker is visible markdown, not an HTML comment, because Linear's editor is
rich text and a marker it stripped would make every run append a duplicate.

The **ledger is the source** — only artifacts recorded as created get linked, so a link
never points at something that does not exist. The ledger is append-only, so pushing the
same cases twice records both; they are listed (they really are both in Testmo) and the
duplicate names are called out as a cleanup job. Matching avoids near-misses deliberately
("Test Run" must not match "Run through test case outline").

The exploratory session's **Mission** is the charter from `04-decision.md` — the
`**Exploratory charter:**` bullet list, carried over as HTML. No charter in the decision
doc means no session, and `plan` warns rather than inventing one.

## Layout

```
tools/            nine scripts and sprint.sh — the facts
.claude/skills/   judgment: ticket-scrape, coverage-check, case-draft
.claude/agents/   case-proofer — independent review in a fresh context
.claude/commands/ /sprint and /rework
docs/             thesis, rollout plan, prompts, Linear setup, handoff, Testmo API map
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
08-import.csv      generated; the Testmo import file
09-run.json        generated; the run manifest — milestone, configs, case ids
review-state.json  case <-> Linear issue, and the comment watermark
CLEANUP.md         everything created outside this folder, with links
created.json       the same ledger, machine-readable
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
| `tools/review_sync.py` | `publish`, `poll`, `watch`, `status`, `stage`, `link` — the Linear review loop |
| `tools/case_export.py` | `build`, `push`, `adopt`, `sync` — approved cases into the Testmo repository |
| `tools/testmo_run.py` | `plan`, `commission` — the milestone, the test run, the exploratory session |
| `tools/ledger.py` | The cleanup record: everything a run created outside its own folder |
| `tools/review_state.py` | Which cases survived review. One source of truth for every tool after it |
| `tools/probe_issues.py` | Throwaway; its answer is now in `docs/TESTMO-API.md`. Safe to delete |

```bash
python3 tools/coverage.py areas pin
python3 tools/coverage.py search "Send Diagnostics"     # search before claiming a gap
python3 tools/review_sync.py stage QA-642               # where did this run stall?
python3 tools/ledger.py QA-642                          # what did this run create?
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

- **Testmo** is REST, and there is no read-only token tier — the token can write. The
  enforcement is *where the write runs*, not what the token can do:
  - **On the VM the allowlist line is `GET`-only, and it stays that way.** `refresh.py` and
    every read tool issue GET. A write attempted here dies as **HTTP 418** before it leaves
    the machine. Don't add a write method to get around that.
  - **Testmo writes run on the Mac**, which has full network, and only from two named
    scripts: `case_export.py push` (create cases) and `testmo_run.py commission` (create
    the milestone and run). Both take a file the model wrote and act on it.
  The shape is deliberate and it is the same one Linear uses below: **the model writes a
  reviewable file, a script holds the token.** A model holding write credentials can do
  anything; a script does a fixed set of operations you can diff.
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
| D½ — commission the run | **Done** — 2026-10-22. Cases into the repository, milestone, test run |
| E — the device leg | Not started. Runs on the Mac, where the phones are |
| F — the evidence view | Not started. Needs E |
| G — reporting out | Not started. Testmo results and the Linear sub-issue |

QA-642 ran the whole loop end to end on 2026-10-21 — ticket to five published cases,
reviewed in Linear, reworked from comments, approved. See
`docs/Claude-Sprint-Workflow-Rollout.md` for the staging and
`docs/Claude-Sprint-Workflow-Thesis.md` for what the remaining stages need.

**Known gaps:**

- The `--on-rework` hook has run only with a human watching. The polling, comment
  detection, rename and republish are all proven; firing `/rework` unattended is not.
- **Release Introduced cannot ride the CSV** — the field has no column in Testmo's import
  or export. `--push` sets it; otherwise it is set by hand in Testmo after import, which is
  what the build warning is reminding you to do.
- Case *quality* has never been measured. Everything proven so far is plumbing: that cases
  get drafted, reviewed, imported and commissioned — not that they are good.

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
