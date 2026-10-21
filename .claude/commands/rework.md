---
description: Revise drafted cases from the Linear review comments, then republish. Called automatically by the sprint watch loop.
argument-hint: <TICKET-ID>
allowed-tools: Bash, Read, Write, Edit, Grep
---

# /rework — fold the review comments back into the cases

Ticket: **$1**

`review_sync.py` has written `runs/$1/06-rework.md`: the cases a reviewer moved to
`In Progress`, with the comments they left. Revise and republish. **This runs unattended
inside the watch loop — do not ask questions, and do not stop to report.**

## 1. Read

- `runs/$1/06-rework.md` — what to change, and who said so
- `runs/$1/02-cases.md` — the cases themselves
- `runs/$1/04-decision.md` — why they exist, so a revision does not contradict the decision

## 2. Revise `02-cases.md`

**The run folder is canonical for case text. Linear is canonical for state and comments.**
Never edit case text in Linear — it will be overwritten on the next publish.

- Change only the cases named in `06-rework.md`. Leave the others untouched.
- Address every comment on a case. If two comments conflict, do what the **later** one
  says and note the conflict in the case's Goals.
- **If a comment asks for something that would be wrong, do not silently comply.** Make the
  change you believe is right, and say plainly in the Goals why it differs from what was
  asked. A reviewer can then move it back with a correction.
- **If a comment cannot be acted on** — it asks for a product decision, or for information
  nobody has — leave the case as it is and add a short `> **Blocked:**` note at the top of
  that case saying what is needed and from whom.
- House rules still apply: platform from the ticket label, Config only when exclusive to a
  form factor, no `Backend:` line, steps numbered `1..n`, a TBD stays unresolved.

## 3. Validate

```
python3 tools/validate_cases.py runs/$1/02-cases.md
```

Must reach 0 errors. Read the duplicate warnings on any case you changed.

## 4. Republish

```
python3 tools/review_sync.py publish $1
```

This updates the sub-issues in place and returns them to `In QA`. Cases already marked
final are skipped and never touched.

## 5. Leave a trail

Append a dated section to `runs/$1/05-proof.md` — which cases changed, which comment drove
each change, and anything you declined to do and why. **Keep it to a few lines per case.**
That file is the record of how the cases got to where they are.
