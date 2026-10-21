---
name: coverage-check
description: Answer "what test coverage already exists for this area of the app, is it still valid, and what's missing?" against the live Testmo case repository. Use whenever a ticket, change, or question concerns an area of the Eleos mobile app and you need to know what is already tested — before writing new cases, when scoping a regression pass, or when someone asks what covers a feature.
---

# Coverage check

Answers the QA question for an area of the app: **what do we already have, is it adequate
for the change at hand, and what's missing?**

```
cd <repo root>                     # the Dispatch-Co-Driver checkout
python3 tools/coverage.py <command>      # query — instant, offline
python3 tools/refresh.py                 # re-pull from Testmo — ~40s, needs network
```

Never read the CSV or the cache JSON into context directly; both are multi-megabyte.

**The commands are shortcuts, not the ceiling.** When a question doesn't fit one, write a
few lines of Python against `testmo-cache.json` instead of forcing it into a command or
answering vaguely. The cache is already normalized — HTML stripped, dropdowns resolved,
folder tree rebuilt, export text merged — so arbitrary queries are cheap and exact. Print
only the aggregate, never the raw records. Questions that want this: manual workload by
area, test-data dependencies in preconditions, flag-to-area maps, external-link rot,
anything comparing across areas or over time.

Per case the useful keys are: `key name area folder_path suite status os automated manual
retired unrunnable has_automation disputed flag_name flag_key flag_state release steps
preconditions expected goal description updated_at archived`.

## Where the data comes from

`refresh.py` pulls the live repository from the Testmo API and writes `testmo-cache.json`.
Every `coverage.py` answer prints its source and age on the first line — **quote that age
when the answer is load-bearing.** Refresh at the start of a ticket; if the cache is more
than a few days old, refresh before trusting a coverage claim.

**Two sources, deliberately.** The API returns only 9 of the 17 fields the template
defines — **Steps, Preconditions and Goal/Purpose are not among them**, and there is no
single-case endpoint. Those three are merged in from the CSV export and are therefore as
old as that export. Everything else — status, suite, folders, flags, new cases — is live.
If step text looks out of date, the fix is a fresh CSV export from Testmo, not a refresh.

**Read-only.** `refresh.py` issues GET only, and the proxy allowlist carries no write
method. Never add one.

## Commands

| Command | Use it for |
|---|---|
| `areas <text>` | **Start here.** Find which area(s) a ticket touches |
| `area "<name>"` | The coverage report for one area |
| `search "<text>"` | Behavior that crosses areas, or when `areas` finds nothing |
| `case <id>` | One case in full — steps, preconditions, expected result |
| `health` | Corpus-wide data quality; only when asked about the data itself |

Flags: `--all` (include retired), `--os Android|iOS`, `--limit N`, `--full` (show steps).

## Never answer "uncovered" from `area` alone

**This is the most expensive mistake this skill can make, and it has been made.** On the
QA-541 run, a coverage review built from three `area` calls concluded that an acceptance
criterion was uncovered and a case was drafted for it. It was covered — by **twelve** cases
in two areas the review never looked at. `search` found them in one call.

The reason is structural. **`area` answers "what is filed here". It cannot answer "what
tests this".** Anything that is used as a *tool* by other features has its coverage filed
under its consumers:

| Subject | Filed under | Also tested from |
|---|---|---|
| Send Diagnostics (Settings) | `Settings` — 8 cases | Scanning (C815193), Dashboard (C770083–C770093) — 12 more |

So, before writing the word *uncovered*, *gap*, or *nothing asserts*:

```
python3 tools/coverage.py search "<the control's shipped name>"
```

**Search by the shipped name, not the ticket's name.** QA-541 called the button "Report
Issue"; the product calls it "Send Diagnostics". The two searches return different sets, and
only one of them is the truth. If the ticket's wording returns little, that is a signal the
feature was renamed — go find the real name in the area dump and search again.

A claim that something is uncovered is the single highest-cost output of this skill: it is
what causes new cases to be written. **Treat it as the claim that needs the most evidence,
not the least.**

## How to read the data — five things that will make you wrong if you skip them

**1. Folders are a tree; the area is the leaf.** Paths look like
`App Messages / Forms > Barcode Testing`, up to 4 deep. `area` matches the leaf name
first and widens only if that finds nothing — it says which it did. A top-level
**`Archive >`** branch exists; cases under it are effectively dead even when their status
says otherwise, and the report flags that.

**2. `Folder` is the area. `Suite` is the iteration.** The same feature reappears under
new suite names as it gets rebuilt — three variants of "App Navigation / Trip Planner"
share folders. Group by folder; use suite to tell which era a case is from. Grouping by
suite scatters an area's coverage, which is how the split gets missed (the Testmo web UI
defaults to grouping by suite).

**3. About 23% of the corpus is retired.** 838 cases are "No Longer Valid", excluded by
default. Say how many were excluded — a large retired set beside a thin live one is
itself the finding.

**4. `Test Case Status` is the authority, and "In Use" means a human runs it.** That is
the manual workload for the area. `has_automation` is a second, weaker signal that
disagrees on ~317 cases; conflicts print with a `*` and are reported as unverified, not
resolved. A live case is in exactly one of three states — `automated`, `manual (In Use)`,
or **neither** (Pending Review / Needs Updated / Pasta, 29 corpus-wide). Never fold
"neither" into "manual".

**5. Remote-config flags are tracked per case, and a blank means "not flag-gated".**
1,006 live cases name a flag, across 4 distinct flags; the area report lists them with
their recorded state. An empty flag field is **information, not missing data** — cases
that need a flag have one. So do not hedge about unflagged cases; treat them as
unconditional. The recorded state is what the case *assumes*, not what is live in QA, so
**confirm the live state before running**. Values are hand-typed and inconsistently cased;
the tool canonicalizes them.

## How to answer

Run `areas` first — do not guess a folder name. Then `area` on each match, with `--full`
when adequacy depends on what the steps actually do, which is often.

- **What exists** — the cases, and what each actually verifies. A count is not a coverage
  answer.
- **Adequacy for this change** — does it break an assumption the existing cases rely on?
  Twenty cases that all assume the old behavior are worse than three that don't.
- **Gaps** — what the change implies that nothing covers.
- **Automated vs manual**, with the caveats above attached.
- **Flags** in play for the area, and that their state needs confirming. Say nothing about
  cases with no flag — a blank means unconditional, not unknown.

## The rule that governs what happens next

**The floor is always a scoped pass on the area that changed** — whether the ticket adds a
feature, upgrades a dependency, or refactors something meant to behave identically. "No new
functionality" means no new *cases*. It never means skip the area. New cases stack on top
of that floor, never replace it.
