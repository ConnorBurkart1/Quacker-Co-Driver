---
name: ticket-scrape
description: Read a Linear ticket and turn it into a filled-in run summary — the structured facts drafting needs, including what the ticket body alone doesn't say. Use when a ticket ID or Linear URL starts a piece of QA work, or when an existing run's 01-summary.md is still blank or stale.
---

# Ticket scrape

Stage C of the sprint loop: a ticket ID goes in, a **filled-in** `01-summary.md` comes out.

```
python3 tools/new_run.py QA-541 --ticket fetched.txt
python3 tools/new_run.py QA-541 --ticket -      # or on stdin
```

**The fetch is your job, not the script's.** `new_run.py` takes ticket *text*; it has no
network and cannot reach Linear. The MCP server lives in the Claude Code session, so the
sequence is always: you call the Linear tools, you write what comes back to a file, you
pass that file to `--ticket`. There is no `--linear` flag and there should not be one — a
deterministic script in `tools/` should not depend on which model is driving it.

### The fetch, in order

1. `get_issue` with an explicit `fields` list — at minimum `title, description, url,
   status, labels, project, team, assignee, createdBy, createdAt, updatedAt`, plus
   `attachments` and `relations` with `includeRelations: true`.
2. `list_comments` for that issue. **Always, even when you expect none.**
3. Write a header block of the Linear metadata, then `---`, then the description verbatim.
4. `new_run.py <TICKET> --ticket <that file>`.

**Record negatives explicitly.** Write `Comments: NONE (0 — checked via list_comments)`,
not nothing. A blank field means "not looked at"; this file is read later by someone who
cannot tell the difference. The same goes for `attachments`, `relations` and linked PRs.

### What the key actually reaches

`Read`-scoped and restricted to the **`QA` team only** — and `QA` is the onboarding team,
not product engineering. `list_teams` returns exactly one team. A ticket on **GRP, DRI,
BUG or EIN** errors with `Could not find referenced Issue`; that is the scoping working,
not a broken server. Those tickets use the paste fallback below.

## What this stage is actually for

It is not "stop pasting". Pasting works. What a paste loses is everything in Linear that
isn't in the description box, and that is where half the testable detail lives.

| Pull | Why it changes the test cases |
|---|---|
| **Comments** | The single most valuable field. ACs marked `PENDING` or `TBD` in the body are usually settled in a comment. QA-276's body says *"UI for where the button lives PENDING"* — drafting off the body alone writes a case against a screen that may not exist. |
| **Labels** | Platform and area tags often live here rather than in the prose. |
| **Project / cycle / milestone** | Resolves **Release Introduced**, which is required on every new case. Resolve it here, not at drafting time. |
| **Linked PRs and branch name** | The only honest signal of what code actually changed. The description says what someone intended; the diff says what shipped. |
| **State and assignee** | A ticket still in progress is not testable yet, and that is worth knowing before drafting fourteen cases. |
| **Relations and sub-issues** | Blocked-by tells you it isn't runnable. Sub-issues tell you where the scope boundary is. |
| **Attachments** | Specs and mockups — the thing "UI TBD" eventually points at. |

## Read-only, and where that is enforced

Two independent locks, **both on Linear's side**: the endpoint is
`https://mcp.linear.app/mcp/readonly`, which only ever exposes read tools, and the key
behind it is restricted to `Read` and to specific teams. The proxy is *not* one of the
locks here — MCP sends every message as a POST to one endpoint, so the method tells it
nothing. See `docs/LINEAR-SETUP.md`.

**Never create an issue, post a comment, change a state, or set an assignee.** The Linear
sub-issue that closes the loop is Stage G, written through a different path, behind gate 4,
after a human says yes. If something seems to want a write now, it is out of scope for this
stage — say so and stop.

## Filling in the Structured block is the job

On both practice runs the Structured block was left blank and drafting read the raw body.
That works, and it throws away the decisions: nothing records which areas were rejected,
whether a flag was checked, or what nobody knew. **A blank field here means "not looked at",
not "not applicable"** — so write the answer or write the reason there isn't one.

| Field | How to fill it | What counts as wrong |
|---|---|---|
| **What changed** | One or two sentences in your own words. If you can't write it without the ticket open, you haven't understood it yet. | Re-quoting the ACs back. |
| **Area(s) touched** | Read `00-candidates.md` as evidence, decide, and **name the plausible candidates you rejected and why.** | A folder name you guessed. Run `coverage.py suggest-file` instead. |
| **New, changed, or meant-to-be-identical** | Three-way, not binary. It decides whether cases get *added*. It never decides whether we test — the floor is always a scoped pass on the area that changed. | Reading "refactor" and writing "no testing needed". |
| **Platforms** | Verbatim from the ticket. "Drive Axle iOS" → iOS. | Inferring from the repo. If the ticket doesn't say, write `<not stated — ask>`. |
| **Config and Backend** | The other two configuration axes. Tickets rarely state them, so this is usually an open question with a name attached — not a blank. | Leaving all three axes empty and letting drafting guess. |
| **Remote config flag** | Name and state, **or the word "none"**. Record it either way. | Empty. In the corpus a blank flag means unconditional; here it means you didn't check. |
| **Release introduced** | From the ticket, else the project/cycle/milestone. | Deferring it — it's required on new cases, and it is harder to find later. |
| **Risk** | What nearby behavior this could plausibly disturb. This is the input to the scoped pass, so it is not decoration. | "Low risk." Name the behavior or leave it to the human. |
| **Open questions** | Everything you would otherwise have guessed, each with a person or team attached. | A question with nobody's name on it doesn't get answered. |

GRP-3163 is the shape to aim at: the ticket is about login, but token rotation touches
**every authenticated request**, so the risk line is the thing that widened the scoped pass
beyond the login screen.

## Check the coverage repository before you believe a PENDING

**This is the lesson of the QA-541 run, and it is the most expensive mistake this stage can
prevent.** QA-541's body carries three acceptance criteria marked `PENDING` or `TBD` and
reads like unbuilt work. All three were already shipped and asserted by existing cases:

| Ticket says | Testmo says |
|---|---|
| "UI for where the button lives PENDING" | C18000 — it is in Settings, labelled **"Send Diagnostics"** |
| "Instructional copy TBD" | C330662 — the copy is shipped and asserted verbatim |
| "Toast message TBD (include offline)" | C330659 "A report has been generated"; C330663, C18003 for offline |

The ticket also used a name the product does not: **"Report Issue"** vs the shipped **"Send
Diagnostics"**. Searching the repository for the ticket's wording finds nothing; searching
for the *behavior* finds thirteen cases.

So: **a `PENDING` in the ticket is a question about the ticket, not a fact about the app.**
Before recording one as an open question, run `coverage.py area` on the area you landed on
and read the case titles. A ticket old enough to have unresolved ACs is old enough for the
feature to have shipped underneath it. Both practice tickets so far were this shape.

**Corollary for `00-candidates.md`:** it ranked Settings nowhere in its top eight on QA-541,
and failed the same way on QA-276. Both tickets carry long implementation appendices
(payload shapes, repo links, curl commands) that outweigh the two sentences describing the
feature. **Treat the scored candidates as evidence that can be wrong**, and when the top
hits look like noise, go find the area by name instead.

## Rules that are not style

- **Quote acceptance criteria, don't paraphrase them.** A paraphrased AC becomes a case
  that tests the paraphrase. Carry the wording across and let drafting work from it.
- **Unresolved in the ticket stays unresolved in the summary.** `PENDING` and `TBD` mean
  the case cannot be written yet. Say which case is blocked on which decision.
- **Never reconcile a contradiction between the body and a comment.** Flag both and let the
  human pick. The comment is usually newer; "usually" is not good enough to draft from.
- **The ticket is a claim about intent, not a description of the code.** If the linked PR
  disagrees with the description, that disagreement is itself a finding.
- **Don't let the summary grow into the cases.** This file is facts and decisions. Steps,
  expected results and house format belong to `case-draft`.

## Then

```
python3 tools/coverage.py suggest-file runs/QA-276/01-summary.md
python3 tools/coverage.py area "<chosen area>" --full | tee runs/QA-276/03-coverage.md
```

Then `case-draft` reads the folder. A correction made in `01-summary.md` propagates to
everything downstream, which is the reason this file exists at all — a wrong summary gets
fixed by editing one file, not by re-explaining in a conversation.

## When Linear isn't reachable

An **HTTP 418 is a proxy block, not a Linear error** — the request never left the VM. Don't
retry it and don't try another Linear endpoint. Report it and ask for:

```
POST https://mcp.linear.app/mcp/readonly
```

One line — POST is how MCP talks, not a write. Full setup in `docs/LINEAR-SETUP.md`.

The same fallback covers any ticket outside the `QA` team, which the key cannot reach by
design: paste the ticket into a file and pass `--ticket`. **Fill in the Structured block
either way** — that half needs no network, and on the evidence so far it is where most of
the value is.
