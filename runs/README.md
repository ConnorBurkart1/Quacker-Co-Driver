# runs/

One folder per ticket. **Everything in here is git-ignored** — a run folder is your working
state on one ticket, not shared history. What gets shared is the Testmo run and the Linear
sub-issue at the end.

Created by:

```
python3 tools/new_run.py QA-276 --ticket /path/to/ticket.txt
```

## The folder is the state

Not the conversation. Every stage reads the previous file off disk, so a session that dies
loses nothing, and a wrong call is fixed by editing the file rather than re-explaining it.

| File | Written by | What it holds |
|---|---|---|
| `STATUS.md` | `new_run.py` | The front door — which stage, what's waiting on a human |
| `00-candidates.md` | `new_run.py --ticket` | Areas scored against the ticket text. Evidence, not an answer |
| `01-summary.md` | you / the ticket scraper | The ticket, plus the structured fields everything downstream reads |
| `02-cases.md` | `case-draft` skill | The drafted cases |
| `03-coverage.md` | `coverage.py area` | What already exists in the area that changed |
| `04-decision.md` | `case-draft` skill | The scoped pass, plus new cases if behavior is new |
| `05-proof.md` | `case-proofer` agent | What independent review disagreed with |

Numbers are the order a human reads them in, not the order they're written.
