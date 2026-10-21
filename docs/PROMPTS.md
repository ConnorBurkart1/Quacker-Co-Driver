# Coverage check — prompts and commands

Two ways in. **Just ask** — the `coverage-check` skill picks it up and runs the right
queries. Or run the commands directly when you want the raw output.

```
cd ~/Lethal/shared/Dispatch-Co-Driver      # Mac
python3 tools/refresh.py                          # re-pull from Testmo, ~40s
python3 tools/coverage.py <command>               # query, instant, offline
```

Refresh at the start of a ticket. Every answer prints its source and age on line one.

---

## Starting from a ticket

> Scrape QA-276 and start a run.

> Pull GRP-3163 — I want the comments and the linked PR, not just the description.

Pasting still works and is the fallback until Linear access lands:

```
pbpaste | python3 tools/new_run.py QA-276 --ticket -     # Mac
python3 tools/new_run.py QA-276 --ticket ticket.txt
```

Either way the job is the same: fill in the **Structured** block of `01-summary.md`. The
raw ticket is only half of it — the other half is what got decided, what was rejected, and
what nobody knows yet. Everything downstream reads that file, so a correction made there
propagates instead of being re-explained.

> The summary says the backend is unknown — that's reference-qa. Fix it and redo the cases.

## Starting a ticket

> What covers the HOS card, and is any of it at risk if we change how the clock banner renders?

> This ticket touches barcode scanning on iOS. What do we already have, what's manual, and what's missing?

> We're upgrading the Genius Scan SDK. No new functionality. What's the scoped pass look like?

The last one is the important one — no new features still means the area gets covered.

## Finding the area first

> Which areas would a change to trip policies touch?

```
python3 tools/coverage.py areas trip
python3 tools/coverage.py areas scan
```

Start here when you're not sure what the folder is called. Areas are a tree now, so the
leaf name is what you search for.

## What do I have to run by hand

> What's the manual workload for Route Options?

> List everything manual in the Dashboard area that isn't automated, with steps.

```
python3 tools/coverage.py area "Route Options"
python3 tools/coverage.py area "Dashboard" --full
```

"Manual" means status **In Use**. Cases that are neither automated nor In Use
(Pending Review, Needs Updated) are reported separately — they're run by nobody.

## Platform-specific

> What barcode coverage is iOS-only?

```
python3 tools/coverage.py area "Barcode Testing" --os iOS
```

## Flags

> What remote config flags are in play for Route Options, and what state do the cases assume?

Flag state in Testmo is what the case *assumes*, not what's live in QA. Confirm before
running. A case with no flag is unconditional — that's information, not a gap.

## Reading a specific case

> Show me C1151 in full.

```
python3 tools/coverage.py case 1151
```

Gives preconditions, steps, expected result, flag, automation status and any dispute.

## Cross-area behavior

> Which cases anywhere mention geofences?

```
python3 tools/coverage.py search geofence
python3 tools/coverage.py search "logged out" --full
```

Use when the behavior doesn't live in one folder.

## Adequacy, not just inventory

> We're changing dismissal so the reminder stays gone after logout. Do any existing cases assume it comes back?

> Twenty cases cover this area — how many of them still hold if we change X?

This is the question the inventory is for. Ask it directly.

## Data quality

> Run a health check on the case repository.

```
python3 tools/coverage.py health
```

Retired counts, automation-field disputes, folders spanning multiple suites, cases with
no steps or no expected result.

---

## Things to know

- **Steps, Preconditions and Goal/Purpose come from the CSV export**, not the API — they're
  as fresh as the last export. Everything else is live. Re-export from Testmo occasionally.
- **`Folder` is the area, `Suite` is the iteration.** The same feature appears under several
  suite names as it gets rebuilt. Testmo's web UI groups by suite by default, which splits
  an area across three places.
- **23% of the repository is retired** and excluded by default. `--all` includes it.
- **Status is the authority on manual vs automated.** `has_automation` disagrees on ~317
  cases; those print with a `*` and should be treated as unverified.
- **Read-only.** `refresh.py` issues GET only and the proxy carries no write method.
