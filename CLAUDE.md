# Quacker / Co-Driver — operating notes

A QA loop for the Eleos mobile app: a Linear ticket goes in, the right test coverage comes
out. `README.md` is what it is; `docs/HANDOFF.md` is where it stands. This file is the
short list of things that have actually gone wrong, so they go wrong once.

## Finish the loop. Publishing is the deliverable.

**`/sprint <TICKET>` ends at publish, not at findings.** Run
`python3 tools/review_sync.py publish <TICKET>` in the same turn as the analysis, before
writing the reply — do not stop after proofing to report what you found and leave
publishing as a second command for Connor.

This has gone wrong once (QA-642) and it is the specific failure `/sprint` exists to
prevent. Interesting findings in a terminal are not the product; a reviewable set of
sub-issues in Linear is. **Publish, then report.**

If the decision is "no new cases", say so plainly and publish nothing. Never invent a case
to have something to publish.

## Never claim something is uncovered from `coverage.py area` alone

`area` answers "what is filed here". It cannot answer "what tests this". Anything used as a
*tool* by other features has its coverage filed under its consumers — Send Diagnostics is
in Settings (8 cases) **and** Scanning and Dashboard (13 more).

Before writing *uncovered*, *gap*, or *nothing asserts*:

```
python3 tools/coverage.py search "<the control's SHIPPED name>"
```

**Search the shipped name, not the ticket's.** QA-642 says "Report Issue"; the product says
"Send Diagnostics". The two searches return different sets and only one is the truth.

## Proofing has caught a material error on every run

Run `case-proofer` on every drafted set, and **confirm every file it reads already exists
before launching it** — on QA-642 it was launched against a blank `01-summary.md` and wasted
a finding saying so.

Both runs so far were wrong in the direction that produced **less work**: QA-541 claimed a
gap that did not exist, QA-642 claimed coverage that was not there. A clean proof is
suspicious, not reassuring. It has also been wrong — verify its central claim yourself
before acting on it.

## Read the ticket's own caveats before concluding "nothing changed"

QA-642 says *"Code was written here but is not scheduled for a release."* An analysis that
assumes the shipped build is current is unsafe while unreleased code exists against the same
feature. Ask before concluding.

Likewise, **a `PENDING` or `TBD` in a ticket body is a question about the ticket, not a fact
about the app.** Check the coverage repository and the sibling sub-issues — on QA-642 two of
three were owned by QA-643 and QA-644, and the rest were answered by shipped cases.

## House rules for drafted cases

- **Platform comes from the ticket's Linear label**, never inferred per case. It rides to
  Linear as a label; `02-cases.md` keeps the `OS:` line because Testmo import needs it.
- **Config only when exclusive to one form factor.** Absent means all.
- **No `Backend:` line.** The client key belongs in Preconditions.
- Steps numbered `1..n`. Preconditions and Expected Results bulleted.
- **A TBD in the ticket stays unresolved in the case.** Assert behavior, not wording.
- `validate_cases.py` must reach 0 errors *when there are cases*. With none it exits 1 with
  `No '## Case:' headings found` — that is the tool idle, not a failure.

## Access — what is enforced where

- **Testmo** is REST with a `GET`-only allowlist line. That line is the entire enforcement:
  there is no read-only token tier. `refresh.py` issues GET only. **Never add a write
  method.**
- **Linear reads** go through `https://mcp.linear.app/mcp/readonly`, which exposes no write
  tool at all. Leave `.mcp.json` pointing there.
- **Linear writes** happen only in `tools/review_sync.py`, over GraphQL, creating and
  updating sub-issues of one named parent. This is deliberate: a model holding `issueCreate`
  can write anything anywhere; a script does a fixed set of operations you can diff. **Do
  not move writes into MCP to save a step.**
- Keep the API key scoped to the **QA** team. It reaches no other team by design.
- `.env` holds `LINEAR_API_KEY` for the Python tools. `.mcp.json` needs it **exported in the
  shell** instead, because the shell expands `${LINEAR_API_KEY}` at server load. Two
  mechanisms, both correct.

## The rule that governs all of it

**The floor is always a scoped pass on the area that changed** — feature, dependency
upgrade, or a refactor meant to behave identically. "No new functionality" means no new
*cases*. It never means skip the area.
