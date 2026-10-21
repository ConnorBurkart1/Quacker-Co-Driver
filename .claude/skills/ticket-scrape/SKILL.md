---
name: ticket-scrape
description: Read a Linear ticket and turn it into a filled-in run summary — the structured facts drafting needs, including what the ticket body alone doesn't say. Use when a ticket ID or Linear URL starts a piece of QA work, or when an existing run's 01-summary.md is still blank or stale.
---

# Ticket scrape

Stage C of the sprint loop: a ticket ID goes in, a **filled-in** `01-summary.md` comes out.

```
python3 tools/new_run.py QA-276 --ticket -     # ticket text on stdin
python3 tools/new_run.py QA-276 --ticket ticket.txt
```

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

Until that lands, the fallback is the one that has been used for every run so far, and it
loses nothing except the comments and the links: paste the ticket into a file and pass
`--ticket`. **Fill in the Structured block either way** — that half needs no network.
