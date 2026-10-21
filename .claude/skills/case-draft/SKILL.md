---
name: case-draft
description: Turn a ticket or change summary into manual test cases in Eleos house style, or into a scoped regression pass when no new cases are warranted. Use when a Linear ticket, a change description, or a feature summary needs test coverage decided and drafted — including when the answer is "no new cases, run these existing ones".
---

# Case draft

Stage B of the sprint loop: a ticket goes in, a **decision** and drafted cases come out.

```
cd <repo root>                     # the Dispatch-Co-Driver checkout
python3 tools/validate_cases.py <cases.md>     # mechanical checks, before any human reads it
```

## The decision comes first, and it is not binary

**The floor is always a scoped pass on the area that changed** — feature, dependency
upgrade, or a refactor meant to behave identically. "No new functionality" means no new
*cases*. It never means skip the area.

So every run produces two lists, one of which is never empty:

| | Always | Only when behavior is new |
|---|---|---|
| **Scoped pass** — existing cases to re-run, plus an exploratory charter | ✓ | ✓ |
| **New cases** for the new behavior | | ✓ |

The failure mode to design against is a ticket filed as "just a refactor" and therefore
tested as nothing.

## The run folder is how stages talk to each other

```
python3 tools/new_run.py LIN-1847 --ticket /path/to/ticket.txt
```

That creates `runs/LIN-1847/` with the ticket in `01-summary.md` and
ranked candidate areas in `00-candidates.md`.

**Determine the area from the ticket — do not ask for it and do not guess a folder
name.** Read the acceptance criteria, the notes, and whatever the ticket is actually
about, then run:

```
python3 tools/coverage.py suggest-file runs/LIN-1847/01-summary.md
```

That scores every area against the ticket text, weighting rare terms over common ones so
a large area cannot win on volume. It prints the distinguishing terms it used, the
matched terms per area, and example cases.

**It ranks; you decide.** The top hit is usually right and sometimes isn't — a ticket
about moving pins scores "Pin" first and "Add stop or via" second, and whether the second
belongs in scope depends on what the ticket actually changes. Name the areas you chose,
and say which plausible candidates you rejected and why. More than one area is normal;
the floor rule applies to every area the change touches.

Then capture the coverage for each chosen area:

```
python3 tools/coverage.py area "Pin" --full | tee runs/LIN-1847/03-coverage.md
``` **Drafting reads those files**, so
the coverage result survives the session that produced it and a human can correct the
summary by editing it rather than re-explaining.

If a run folder already has `03-coverage.md`, read it instead of re-running the lookup —
unless the cache has been refreshed since, in which case say so and re-run.

## Before drafting anything

0. **Never draft off a truncated listing.** `area` prints 40 cases by default and sorts
   by title; a feature whose cases start with "Report" or "Send" is invisible behind an
   `A`–`D` page. Pass `--limit 200`, and **search the area for the feature's own nouns**
   before writing anything:

   ```
   python3 tools/coverage.py area "Settings" --limit 200
   python3 tools/coverage.py search "report issue"
   python3 tools/coverage.py search "diagnostics"
   ```

   A shipped feature is often filed under the label the app actually uses, not the words
   the ticket uses. A ticket saying "Report Issue" can be covered by cases called "Send
   Diagnostics". Search two or three plausible names before concluding anything is new.

1. **Have the coverage answer in hand.** Read `03-coverage.md`, or run the
   `coverage-check` skill and write its output there. Never draft blind — you need to
   know what exists, what it asserts, and what is manual.
2. **Decide whether existing cases still hold.** A change that invalidates an assumption
   twenty cases rely on is more important than any new case you could write.
3. **Check the flag.** If the area is flag-gated, a new case must say which flag state it
   assumes. Cases usually exist in pairs — one per state — so decide whether you need one
   or both.

## The format

**This is the standard for new cases. Existing cases are not expected to match it** —
plenty predate it and will not be backfilled. Use the corpus to learn what exists and to
avoid duplicating it, not as a style authority.

Median 6 steps (p90 13). Titles are descriptive sentences, median 61 chars, usually
opening with a verb or condition: *Verify…*, *Tapping…*, *If…*, *When…*, *Ensure…*.

**The `(Result N)` convention is the thing that makes a case executable.** Steps carry an
inline marker at the point where verification happens; Expected keys back to it. A reader
must never have to guess where to check.

This is the team template, written in the form the validator reads:

```markdown
## Case: Moving a stop pin while offline retains the new location after reconnect
- **Status:** In Use
- **Area:** Pin
- **Suite:** App Navigation/Trip Planner (New TBT/ New Route Options)
- **OS:** All (not restricted)
- **Config:** Android Phone, iOS Phone (iPhone)
- **Backend:** reference-qa
- **Flag:** use_form_route_options_v2 = True
- **Release:** 1.66

### Preconditions
- USER: PINMOVE-1
- Load with at least two stops assigned
- Navigate to the Firebase Remote Config page. Verify the flag config matches {true}
- Load setup, as a JSON spec where one exists — and say which fields must hold the
  stated value versus which may be anything

### Steps
1. Log into PINMOVE-1 and wait for sync
2. Put the device in airplane mode
3. Long press a stop pin, drag it, and accept (Result 1)
4. Restore connectivity and reopen the load (Result 2)

### Expected Results
- **Result 1** = The pin shows at the new location and the address updates locally

- **Result 2** = The moved location persists and matches the server

### Goals
What scenario this tests, and whether it is smoke or recurring. Settle this with
engineering rather than guessing.

### JSON Assets
Any asset the case needs, saved as a JSON file beside the case.
```

**Section order is fixed: Preconditions → Steps → Expected Results → Goals.**

**Steps are numbered, 1..n, in order.** A tester reports "it failed on step 4" and a
reviewer asks "what does step 2 assume" — neither works if the steps are bullets. The
validator treats a bulleted step as an error. Preconditions and Expected Results stay
bulleted: they are a set, not a sequence. Each Result is its own bullet with a blank line
between, so a tester reading on a phone can tell them apart.

**Write the fields the way the team writes them. The validator translates to what Testmo
stores and prints what each one will import as.**

| Write | Imports as |
|---|---|
| Status: `Manual` | `In Use` — same thing, Testmo's label differs |
| Flag State: `on` / `off` | `True` / `False` |
| Release: `release-1.66` | `1.66` |

## Configuration is three separate axes — do not collapse them

| Field | Question it answers | Values |
|---|---|---|
| **OS** | Where the case *may* run | `All (not restricted)` · `Android` · `iOS` |
| **Config** | Which device profiles it *is* run against | the seven Testmo configurations |
| **Backend** | Which environment it runs against | `reference-qa`, `staging`, `production`, a named host |

**OS** is 99% populated and coarse. **Config** is Testmo's own Configurations feature and
only 172 live cases set one — so most of the corpus is silent about phone versus tablet,
which is a real gap rather than a convention. The seven defined values are:

```
Android          Android Phone       Android Tablet
iOS              iOS Phone (iPhone)  iOS Tablet (iPad)
Android & iOS
```

The validator checks these against the live list and rejects an OS/Config contradiction —
`OS: Android` with `Config: iOS Tablet (iPad)` is an error, not a warning.

**Set Config whenever the case is device-shaped.** Anything touching layout, rotation,
split view, camera, or a control whose position differs between phone and tablet needs
it. "All (not restricted)" with no Config means "runs everywhere", which is usually
untrue and untested.

**Backend has no Testmo field yet.** State it in the metadata and in Preconditions until
someone adds a custom field. The environments cases actually name are `reference-qa`
(740 cases — the default client key), `staging` (211), `squid-fortress-staging`,
`dashboard-staging.eleostech.com`, `axle-test.eleostech.com`,
`internal-admin-staging.eleostech.com` and `production` (32). **A case that reads a
server-side result is not runnable without one** — the IA lookup on QA-276 is keyed on
client key, and a tester on the wrong environment finds nothing and reports a false
failure.

**When the ticket tags a platform or environment, carry it through verbatim.** Do not
infer `OS: iOS` from a ticket that says "Drive Axle iOS" and then leave Config and Backend
blank — the ticket has told you two of the three axes, so fill in what it gave you and ask
about the third.

**Release Introduced is required on new cases.** Only 11% of the historical corpus has it,
which is why the field looks optional — it isn't, going forward. Put the version the
feature ships in.

**Two fields carry instructions, and they are not decoration.** *Expected Results* says
*confirm with Product* — so an expected result you inferred rather than confirmed is an
assumption, and must be marked as one for the human gate. *Goals* says *discuss with
engineering* — smoke versus recurring changes where the case belongs.

**A unique user per case**, per the template. Reusing a heavily shared account — some are
on 40+ cases — couples your case to someone else's state. If you do not know which account, write `USER: <needed — specify>` and let the
gate resolve it. **Never invent one** — that produces a case nobody can run.

A single-assertion case may skip the markers and give Expected as one plain sentence.
Beyond about six steps, markers are required.

**Preconditions name a USER.** 99% of the corpus has preconditions; 85% name a test
account. If you do not know which account, write `USER: <needed — specify>` rather than
inventing one. Inventing a test account produces a case nobody can run.

## Rules that are not style

- **One case covers one thing.** Over ~15 steps it is two cases.
- **Assert only what the case is about.** Incidental assertions make failures ambiguous.
- **Never write a case around a known bug.** If current behavior is wrong, the case
  describes correct behavior and the bug gets filed.
- **No coordinates.** Ever, in a written case.
- **Exact field values only** — Area, Suite, OS and Flag must match the repository
  character for character. The validator checks this because the real values contain
  traps: `App Navigation / Trip Planner (New TBT))` has spaces around the slash and a
  doubled closing paren.

## Then validate, then proof

1. `python3 tools/validate_cases.py <file>` — fix every ERROR. Warnings are judgment calls.
2. **Proof with a fresh instance** using the `case-proofer` agent. Give it the ticket,
   the path to the cases, and the validator's output. **Do not give it your reasoning** —
   a reviewer handed your conclusion confirms it. The disagreements are where human
   attention is worth spending.

   Handing over the validator output matters for cost as well as quality: the duplicate
   hunt is already done mechanically, so the proofer reads a handful of named cases
   instead of dumping a whole area. In an agent loop every tool result is carried through
   every later turn, so one oversized dump is paid many times over.
3. Only then does a human read it. That is gate 2.

## Output

Write to the run folder, never only to the conversation:

```
runs/<TICKET>/
  STATUS.md        what stage, what is waiting on a human, what the next command is
  01-summary.md    the ticket, structured
  02-cases.md      drafted cases in the format above
  03-coverage.md   what already exists, from the coverage check
  04-decision.md   scoped pass + new cases, with the reasoning
  05-proof.md      the proofer's disagreements
```

The folder is the state. A session that dies loses nothing, and a wrong summary is fixed
by editing `01-summary.md` rather than re-explaining.
