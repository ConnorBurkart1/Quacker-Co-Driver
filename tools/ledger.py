#!/usr/bin/env python3
"""
ledger.py — the cleanup record for one run.

Every script in this repo that creates something outside the run folder — a Linear
sub-issue, a Testmo case, a milestone, a test run — records it here. The loop is still
being debugged, so a restart means deleting whatever the last attempt left behind, and
nothing is worse to clean up than an artifact you did not know got made.

Two files, same facts:

    runs/<TICKET>/CLEANUP.md    for a human with a browser open — titles and URLs
    runs/<TICKET>/created.json  for a script

Both are append-only. Deleting the thing in Testmo or Linear does not remove the line;
tick it in CLEANUP.md instead, so the record of what existed survives the cleanup.

    from ledger import record
    record("QA-642", "testmo-case", [{"id": 834122, "name": "…"}])
"""

import json
import os
import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LINEAR_URL = "https://linear.app/eleos-technologies/issue/{identifier}"
TESTMO_URL = "https://eleostechnologies.testmo.net"

# kind -> (heading, how to build a URL from the item)
KINDS = {
    "linear-issue": ("Linear sub-issues",
                     lambda i: LINEAR_URL.format(identifier=i.get("identifier", ""))),
    "testmo-case": ("Testmo cases",
                    lambda i: f"{TESTMO_URL}/repositories/case/{i.get('id')}"),
    "testmo-milestone": ("Testmo milestones",
                         lambda i: f"{TESTMO_URL}/milestones/view/{i.get('id')}"
                                   if i.get("id") else ""),
    "testmo-run": ("Testmo runs",
                   lambda i: f"{TESTMO_URL}/runs/view/{i.get('id')}" if i.get("id") else ""),
}


def _paths(ticket):
    folder = os.path.join(ROOT, "runs", ticket)
    return (os.path.join(folder, "created.json"),
            os.path.join(folder, "CLEANUP.md"), folder)


def load(ticket):
    js, _, _ = _paths(ticket)
    if not os.path.isfile(js):
        return {"ticket": ticket, "entries": []}
    with open(js, encoding="utf-8") as f:
        return json.load(f)


def record(ticket, kind, items, note=""):
    """Append created artifacts. Items are dicts with at least id or identifier."""
    if not items:
        return
    js, md, folder = _paths(ticket)
    if not os.path.isdir(folder):
        raise FileNotFoundError(f"no run folder at runs/{ticket}/")

    data = load(ticket)
    when = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    known = {(e["kind"], str(e.get("id") or e.get("identifier")))
             for e in data["entries"]}
    added = []
    for it in items:
        key = (kind, str(it.get("id") or it.get("identifier")))
        if key in known:
            continue
        entry = dict(it)
        entry.update({"kind": kind, "created_at": when})
        if note:
            entry["note"] = note
        data["entries"].append(entry)
        added.append(entry)
    if not added:
        return

    with open(js, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    _render(ticket, data, md)
    return added


def _render(ticket, data, md):
    heading, _ = KINDS.get("linear-issue")
    lines = [f"# {ticket} — what this run created",
             "",
             "Everything made outside the run folder, so a restart can be cleaned up.",
             "Tick a box when you have deleted it; the line stays as the record that it",
             "existed. Appended automatically — do not hand-edit the entries.",
             ""]
    by_kind = {}
    for e in data["entries"]:
        by_kind.setdefault(e["kind"], []).append(e)

    for kind, (title, url_for) in KINDS.items():
        rows = by_kind.get(kind)
        if not rows:
            continue
        lines += [f"## {title} ({len(rows)})", ""]
        for e in rows:
            ident = e.get("identifier") or e.get("id")
            name = e.get("name") or e.get("title") or ""
            url = url_for(e)
            label = f"`{ident}`" + (f" [link]({url})" if url else "")
            lines.append(f"- [ ] {label} — {name}"
                         + (f"  _{e['note']}_" if e.get("note") else ""))
        lines.append("")

    leftover = set(by_kind) - set(KINDS)
    for kind in sorted(leftover):
        lines += [f"## {kind} ({len(by_kind[kind])})", ""]
        for e in by_kind[kind]:
            lines.append(f"- [ ] `{e.get('id') or e.get('identifier')}` — "
                         f"{e.get('name') or e.get('title') or ''}")
        lines.append("")

    with open(md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def summary(ticket):
    """One line per kind, for a script to print after it creates things."""
    data = load(ticket)
    if not data["entries"]:
        return "nothing recorded as created."
    by = {}
    for e in data["entries"]:
        by.setdefault(e["kind"], []).append(e.get("identifier") or e.get("id"))
    out = []
    for kind, ids in by.items():
        shown = ", ".join(str(i) for i in ids[:12])
        more = f" (+{len(ids) - 12} more)" if len(ids) > 12 else ""
        out.append(f"  {kind}: {shown}{more}")
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        sys.exit("usage: ledger.py <TICKET>   — print what this run created")
    print(f"{sys.argv[1]} — created artifacts")
    print(summary(sys.argv[1]))
