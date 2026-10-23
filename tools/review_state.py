#!/usr/bin/env python3
"""What survived review, read from runs/<TICKET>/review-state.json.

`02-cases.md` is canonical for case *text*. Linear is canonical for the *verdict*: moving
a sub-issue to Canceled means do not ship that case. Every tool downstream of review has
to agree about that, and when they disagreed the failures were silent or fatal:

  - `case_export.py build/push` imported a case the reviewer had canceled.
  - `case_export.py adopt` hunted for it in the cache, never found it, and exited 1,
    which killed the run before the milestone, run and session were ever created.
  - `testmo_run.py commission` refused to run because that case had "no Testmo id yet".

One source of truth, imported by all of them, so the next tool downstream cannot forget.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def dropped_titles(ticket):
    """Lower-cased titles the reviewer canceled. Empty when there is no review yet."""
    path = os.path.join(ROOT, "runs", ticket, "review-state.json")
    if not os.path.isfile(path):
        return set()
    try:
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError):
        return set()
    return {t.strip().lower() for t, r in (state.get("cases") or {}).items()
            if isinstance(r, dict) and r.get("status") == "dropped"}


def drop_rejected(ticket, cases, key="title"):
    """Split cases into (kept, rejected-titles). `key` names the title field."""
    dropped = dropped_titles(ticket)
    if not dropped:
        return list(cases), []
    kept, gone = [], []
    for c in cases:
        title = (c.get(key) or "").strip()
        (gone if title.lower() in dropped else kept).append(
            title if title.lower() in dropped else c)
    return kept, gone
