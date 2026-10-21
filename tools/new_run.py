#!/usr/bin/env python3
"""
new_run.py — start a run folder for a ticket, and seed it with the coverage answer.

The run folder is the state. Drafting reads from it, proofing reads from it, and a human
corrects it by editing a file rather than re-explaining in a conversation. A session that
ends loses nothing.

    python3 tools/new_run.py LIN-1847
    python3 tools/new_run.py LIN-1847 --linear               fetch the ticket from Linear
    python3 tools/new_run.py LIN-1847 --ticket ticket.txt    seed the summary, suggest areas
    python3 tools/new_run.py LIN-1847 --ticket -             ... from stdin, for a scrape
    python3 tools/new_run.py LIN-1847 --area "Pin"           seed 03-coverage.md directly
    python3 tools/new_run.py LIN-1847 --area "Pin" --full    include steps in the coverage dump

With --ticket, the area is NOT chosen for you. The ticket text is scored against every
area and the ranked candidates are written to 00-candidates.md as evidence. Which area
the ticket actually touches is a judgment call made from that evidence.

Creates runs/<TICKET>/ with STATUS.md and 01-summary.md, and writes the
coverage report to 03-coverage.md so drafting has it on disk rather than in context.
"""

import os
import subprocess
import sys
from datetime import date

Q_FETCH = """
query($id: String!) {
  issue(id: $id) {
    identifier title description url createdAt updatedAt
    state { name } labels { nodes { name } } project { name } team { key }
    assignee { name } creator { name } parent { identifier title }
    children { nodes { identifier title } }
    attachments { nodes { title url } }
    relations { nodes { type relatedIssue { identifier title } } }
    comments { nodes { body createdAt user { name } } }
  }
}"""


def fetch_from_linear(ticket):
    """Pull a ticket over the GraphQL API and render it the way a scrape should.

    This exists because the API is now reachable. The earlier rule — 'the fetch is the
    model's job' — was about MCP, which only a model client can speak. A GraphQL call is
    deterministic and belongs in tools/ like every other fact-gathering step.

    Records negatives explicitly: 'Comments: NONE' is a finding, a blank line is not.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import review_sync
    issue = review_sync.gql(Q_FETCH, {"id": ticket})["issue"]
    if not issue:
        sys.exit(f"Linear has no issue {ticket} — or the key cannot see its team.")

    def names(node, key="name"):
        return [n[key] for n in issue[node]["nodes"]] if issue.get(node) else []

    comments = issue["comments"]["nodes"]
    atts = issue["attachments"]["nodes"]
    rels = issue["relations"]["nodes"]
    kids = issue["children"]["nodes"]
    out = [issue["title"], "",
           "[Linear metadata — fetched over the API, not present in a paste]",
           f"- Identifier: {issue['identifier']}",
           f"- URL: {issue['url']}",
           f"- Status: {issue['state']['name']} / Team: {issue['team']['key']}",
           f"- Labels: {', '.join(names('labels')) or 'NONE'}",
           f"- Project: {(issue.get('project') or {}).get('name', 'none')}",
           f"- Created by: {(issue.get('creator') or {}).get('name', '?')}"
           f" on {issue['createdAt'][:10]} / Updated: {issue['updatedAt'][:10]}",
           f"- Assignee: {(issue.get('assignee') or {}).get('name', 'none')}"]
    if issue.get("parent"):
        out.append(f"- Parent: {issue['parent']['identifier']} "
                   f"{issue['parent']['title']!r}")
    out.append("- Sub-issues: " + (", ".join(
        f"{k['identifier']} {k['title']!r}" for k in kids) if kids else "NONE"))
    out.append("- Attachments: " + (", ".join(
        f"{a['title']} <{a['url']}>" for a in atts) if atts else "NONE"))
    out.append("- Relations: " + (", ".join(
        f"{r['type']} {r['relatedIssue']['identifier']}" for r in rels)
        if rels else "NONE"))
    out.append(f"- Comments: {len(comments) or 'NONE'}"
               + (" — reproduced below" if comments else " (checked, there are none)"))
    out += ["", "---", "", (issue.get("description") or "(no description)").strip()]
    if comments:
        out += ["", "---", "", "### Comments, oldest first"]
        for c in comments:
            who = (c.get("user") or {}).get("name", "unknown")
            out += ["", f"**{who}** — {c['createdAt'][:16].replace('T', ' ')}", "",
                    c["body"].strip()]
    print(f"  fetched {issue['identifier']} from Linear — "
          f"{len(comments)} comment(s), {len(atts)} attachment(s), "
          f"{len(kids)} sub-issue(s)")
    return "\n".join(out) + "\n"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)          # repo root: .env, the cache and runs/ live here
RUNS = os.path.join(ROOT, "runs")

SUMMARY = """# {ticket} — summary

Paste or write the ticket here, then fill in the fields below. Everything downstream
reads this file, so a correction made here propagates. Fix it here rather than in a
conversation.

## The ticket

<paste the Linear ticket text>

## Structured

- **What changed, in plain language:**
- **Area(s) of the app touched:**
- **New functionality, or a change to existing code?**
  (This decides whether we *add* cases. It never decides whether we test — the floor is
  always a scoped pass on the area that changed.)
- **Platforms (OS):** Android / iOS / both — verbatim from the ticket, never inferred
- **Config:** phone / tablet / a named device profile, or "not stated — ask"
- **Backend:** reference-qa / staging / production, or "not stated — ask"
- **Remote config flag:** name and state, or "none" — record it either way
- **Release introduced:**
- **Risk — what nearby behavior could this plausibly disturb:**
- **Open questions for a human:**
"""

STATUS = """# {ticket} — status

Started {today}.

| Stage | State |
|---|---|
| 1. Summary | ⬜ `01-summary.md` — fill it in |
| 2. Cases drafted | ⬜ `02-cases.md` |
| 3. Coverage checked | {cov} |
| 4. Decision | ⬜ `04-decision.md` — scoped pass, plus new cases if behavior is new |
| 5. Proofed | ⬜ `05-proof.md` — `case-proofer` agent |
| 6. Human review | ⬜ **gate 2** |
| 7. Executed | ⬜ |
| 8. Reported | ⬜ |

## Next

Fill in `01-summary.md`, then ask for cases. The `case-draft` skill reads this folder.

```
cd {root}
python3 tools/coverage.py area "<area>" --full | tee runs/{ticket}/03-coverage.md
python3 tools/validate_cases.py runs/{ticket}/02-cases.md
```
"""


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 1
    ticket = args[0].strip().upper()
    area = None
    if "--area" in argv:
        i = argv.index("--area")
        if i + 1 < len(argv):
            area = argv[i + 1]
    ticket_file = None
    if "--ticket" in argv:
        i = argv.index("--ticket")
        if i + 1 < len(argv):
            ticket_file = argv[i + 1]
    full = "--full" in argv

    if "--linear" in argv and not ticket_file:
        ticket_file = None  # handled below; keeps the candidate-scoring path alive

    folder = os.path.join(RUNS, ticket)
    if os.path.isdir(folder):
        print(f"{folder} already exists — leaving it alone.")
        print("Delete it by hand if you really want to start over.")
        return 1
    os.makedirs(folder)

    ticket_text = ""
    if "--linear" in argv:
        ticket_text = fetch_from_linear(ticket)
        ticket_file = ticket_file or "linear"
    if ticket_file and not ticket_text:
        if ticket_file == "-":
            ticket_text = sys.stdin.read()
        elif os.path.isfile(ticket_file):
            ticket_text = open(ticket_file, encoding="utf-8").read()
        else:
            print(f"No such file: {ticket_file}")
            return 1

    # Score candidates from whatever text we ended up with, whether it came off disk,
    # off stdin or off the Linear API. This used to live inside the file-reading branch,
    # so --linear produced a run folder with no 00-candidates.md at all.
    if ticket_text:
        out = subprocess.run(
            [sys.executable, os.path.join(HERE, "coverage.py"), "suggest",
             ticket_text, "--limit", "8"],
            capture_output=True, text=True,
        )
        with open(os.path.join(folder, "00-candidates.md"), "w",
                  encoding="utf-8") as fh:
            fh.write(f"# {ticket} — candidate areas\n\n")
            fh.write("Scored against the repository from the ticket text. **These are "
                     "evidence, not an answer** — which area the ticket actually "
                     "touches is a judgment call.\n\n```\n")
            fh.write(out.stdout.rstrip() + "\n```\n")
        print("  wrote 00-candidates.md")

    cov_state = "⬜ not run"
    if area:
        out = subprocess.run(
            [sys.executable, os.path.join(HERE, "coverage.py"), "area", area]
            + (["--full"] if full else []) + ["--limit", "200"],
            capture_output=True, text=True,
        )
        if out.returncode == 0 and out.stdout.strip():
            with open(os.path.join(folder, "03-coverage.md"), "w",
                      encoding="utf-8") as fh:
                fh.write(f"# {ticket} — existing coverage for {area!r}\n\n")
                fh.write("Generated by `coverage.py`. Re-run it if the cache is stale.\n")
                fh.write("\n```\n" + out.stdout.rstrip() + "\n```\n")
            cov_state = f"✅ `03-coverage.md` — area {area!r}"
            print(f"  wrote 03-coverage.md for {area!r}")
        else:
            print(f"  coverage lookup for {area!r} returned nothing; skipping")
            print(f"  try: python3 coverage.py areas {area.split()[0].lower()}")

    summary = SUMMARY.format(ticket=ticket)
    if ticket_text:
        summary = summary.replace("<paste the Linear ticket text>", ticket_text.strip())
    with open(os.path.join(folder, "01-summary.md"), "w", encoding="utf-8") as fh:
        fh.write(summary)
    with open(os.path.join(folder, "STATUS.md"), "w", encoding="utf-8") as fh:
        fh.write(STATUS.format(ticket=ticket, today=date.today().isoformat(),
                               cov=cov_state, root=ROOT))

    print(f"\n{folder}")
    print("  STATUS.md        the front door")
    print("  01-summary.md    fill this in first")
    if area:
        print("  03-coverage.md   what already exists")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
