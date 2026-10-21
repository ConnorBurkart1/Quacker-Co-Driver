---
description: Run the full QA loop for one Linear ticket — fetch, summarize, check coverage, draft cases, validate, publish to Linear for review.
argument-hint: <TICKET-ID> [--no-publish]
allowed-tools: Bash, Read, Write, Edit, Grep, Task
---

# /sprint — one ticket, start to reviewable

Ticket: **$1**

Run the loop for `$1`. The deterministic steps are scripts; the judgment between them is
yours. Do not ask permission between stages — the review gate is in Linear, after
publishing, not in this conversation.

## Scope — what this command does and does not do

**It covers Stages A–C only: ticket in, reviewable case set out.** It ends at publish.

| In | Out, and why |
|---|---|
| Fetch, summarize, coverage, decide, draft, validate, proof, publish | **Stage E — execution.** Needs a device. Runs on the Mac, not here |
| | **Stage F — evidence.** Needs E to have run |
| | **Stage G — Testmo results and the Linear sub-issue.** Write access, behind its own gate |

Stages 7 and 8 in `STATUS.md` (Executed, Reported) stay unchecked when this finishes. That
is correct, not an incomplete run. **Never mark them, and never write results to Testmo** —
`refresh.py` is GET-only and must stay that way.

## 1. Fetch and seed

```
python3 tools/new_run.py $1 --linear
```

If `runs/$1/` already exists the script refuses. That is deliberate: say so, show what is
in the folder, and ask whether to resume or start over. Do not delete it yourself.

## 2. Fill `01-summary.md`

Follow `.claude/skills/ticket-scrape/SKILL.md`. Every field in the Structured block gets an
answer or a stated reason there isn't one — **a blank means "not looked at"**.

Three things that have caught every run so far:

- **Platform comes from the ticket's label**, not from reading the cases. Never infer it.
- **Read `00-candidates.md` as evidence, not as an answer.** On tickets with a long
  implementation appendix it has ranked the real area nowhere in its top eight, three times
  running. If the top hits look like noise, find the area by name instead.
- **Check sub-issues for owners.** A `PENDING` or `TBD` in the body is often a sibling task
  already in flight, not an unanswerable question. Name the sub-issue that owns it.

## 3. Check coverage

Follow `.claude/skills/coverage-check/SKILL.md`. Write `runs/$1/03-coverage.md`.

**Never conclude "uncovered" from `coverage.py area` alone.** Search the corpus by the
control's *shipped* name before claiming any gap — this is the mistake that produced a
duplicate case on QA-541, and the shipped name is often not the ticket's name.

## 4. Decide, then draft

Follow `.claude/skills/case-draft/SKILL.md`. Write `runs/$1/04-decision.md` and
`runs/$1/02-cases.md`.

The floor is always a scoped pass on the area that changed. **"No new functionality" means
no new cases — it never means skip the area.** If existing coverage already asserts the
behavior, say so and write no cases; that is a valid and common outcome.

House rules for the file:
- **OS** stays in the file (Testmo import needs it) — `review_sync.py` lifts it to a Linear
  label on publish.
- **Config** only when a case is exclusive to one form factor. Absent means all.
- **No Backend line.** The client key belongs in Preconditions.
- Steps numbered `1..n`; Preconditions and Expected Results bulleted.
- A `TBD` in the ticket stays unresolved in the case. Assert behavior, not wording.

## 5. Validate

```
python3 tools/validate_cases.py runs/$1/02-cases.md
```

**Must reach 0 errors** *when there are cases to check.* If the decision is "no new
cases", the validator exits 1 with `No '## Case:' headings found` — that is the tool having
nothing to do, not a failure. Note it and move on.

Warnings are judgment calls — read the duplicate warnings especially, and either cite the
overlapping case in the Goals or drop the case.

## 6. Proof

**Before launching it, confirm every file it will read already exists on disk:**
`00-candidates.md`, `01-summary.md`, `02-cases.md`, `03-coverage.md`, `04-decision.md`.
On the QA-642 run the proofer was launched while `01-summary.md` was still the blank seed
template, and it spent a whole finding reporting the summary as empty. **A proof of files
you have not finished writing is wasted.**

Launch the `case-proofer` agent on the folder. Give it the files and the central claim to
attack — not your reasoning. Apply what survives; record what you rejected and why in
`runs/$1/05-proof.md`.

It has caught a material error on **every** run so far, and both times the draft was wrong
in the direction that produced less work — QA-541 claimed a gap that did not exist, QA-642
claimed coverage that was not there. **Treat a clean proof as suspicious, not as
confirmation.** Re-verify its central claim yourself before acting on it; it has also been
wrong.

## 7. Publish for review — always, in the same turn

**This step is not optional and is not a suggestion to hand back to Connor.** Unless
`--no-publish` was passed explicitly, run it yourself before you write your reply:

```
python3 tools/review_sync.py publish $1
```

The parent is found automatically — the "Create a test case outline" sub-issue.

**Do not stop after proofing to report findings and leave this for a second command.**
That happened on QA-642 and is exactly what `/sprint` exists to prevent. Findings are
interesting; a published, reviewable set is the deliverable. Publish, then report.

**If there are no cases to publish**, say so plainly — a "no new cases" decision is a
valid and common outcome, and `review_sync.py` will have nothing to create. Do not invent
a case to have something to publish.

Then tell Connor, in a few lines: how many cases, what the decision was, what is blocked
and on whom, and this command:

```
python3 tools/review_sync.py watch $1 --interval 120
```

## Then — the review loop

`In QA` is awaiting review. `Product Review` / `Done` is final. `In Progress` **with a new
comment** means rework. When `runs/$1/06-rework.md` appears, revise `02-cases.md` from the
comments in it, then publish again. Never edit case text in Linear — the run folder is
canonical for text, Linear for state and comments.
