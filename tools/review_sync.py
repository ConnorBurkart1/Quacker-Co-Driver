#!/usr/bin/env python3
"""
review_sync.py — publish drafted cases to Linear as sub-issues, then watch the review.

Stage D, done in Linear instead of a bespoke HTML view. Each drafted case becomes one
sub-issue under a parent. A QA lead reviews by moving the sub-issue and leaving comments.
This script turns those moves into a rework queue on disk; Claude reads the queue, revises
`02-cases.md`, and the script republishes.

    python3 review_sync.py publish QA-541 --parent QA-647 --dry-run
    python3 review_sync.py publish QA-541 --parent QA-647
    python3 review_sync.py poll    QA-541              one-shot read, writes the queue
    python3 review_sync.py watch   QA-541 --interval 30
    python3 review_sync.py watch   QA-541 --on-rework "claude -p '/rework QA-541'"
    python3 review_sync.py status  QA-541              print the board, write nothing
    python3 review_sync.py stage   QA-541              which stage is next, for resuming

WHY THIS IS A SCRIPT AND NOT MCP WRITE TOOLS
    The agent session stays on https://mcp.linear.app/mcp/readonly and keeps no write
    tool at all. Every write in this workflow happens here, in code that can be read and
    diffed, doing a fixed set of operations. A model with issueCreate in its tool list can
    write anything, anywhere, at any time; this script creates and updates sub-issues of
    one named parent and nothing else. The blast radius is the diff, not the judgment.

    GraphQL is POST-only, so the proxy cannot enforce read-only the way it does for
    Testmo. Enforcement here is this file plus the key's team scope. Keep the key scoped
    to the QA team.

Reads LINEAR_API_KEY from .env beside the repo root, or from the environment — same
pattern as refresh.py. (.mcp.json is the exception: it needs the key exported in the
shell, because the shell is what expands ${LINEAR_API_KEY} at server load. A Python tool
has no such constraint.) .env is git-ignored; keep it that way.
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RUNS = os.path.join(ROOT, "runs")
API = "https://api.linear.app/graphql"

# The state machine. Claude writes a case and parks it in AWAITING; a human moves it.
AWAITING = "In QA"                         # with Claude / awaiting review
FINAL = {"Product Review", "Done"}         # approved, locked, never touched again
REWORK = {"In Progress", "In Review"}      # explicitly handed back
DROPPED = {"Canceled"}                     # drop the case

# A new comment from a human IS the instruction, whatever the state says. Requiring a
# particular state as well means a reviewer who comments without moving the issue gets
# silence — which is what happened on QA-679: the comment said "add the word Banana to the
# end of title", the issue sat in `In Review`, and nothing fired. State is for approving;
# comments are for changing.
#
# Do NOT filter review comments by author. The key is Connor's, so `viewer` IS Connor —
# "ignore my own comments" silently discarded every comment that mattered. Anything this
# script posts is prefixed with BOT_MARK instead, and only that is excluded.
BOT_MARK = "[co-driver]"

# The OS axis moves out of the case body and onto the issue as a Linear label, so a lead
# can filter the board by platform. "All (not restricted)" gets BOTH labels rather than
# none: filtering for Android should return every case that runs on Android, including the
# unrestricted ones. Absence of a label would quietly exclude them.
OS_LABELS = {
    "Android": ["Android"],
    "iOS": ["iOS"],
    "All (not restricted)": ["Android", "iOS"],
}

# Platform is a property of the TICKET, not something inferred per case: QA-642 carries
# the `Android` label and that settles it for every case drafted from it. The publish
# parent is the wrong place to look — QA-647 is unlabelled. So we read the run's own
# ticket and inherit. A case-level OS line can still narrow it, never widen it.
PLATFORM_LABELS = {"Android", "iOS", "App Manager"}

# The template puts a "Create a test case outline" sub-issue under every story, so the
# publish parent can be found rather than typed. Saves a flag and removes the chance of
# publishing eight cases under the wrong issue.
# "Run through test case outline" is a sibling task and also matches the bare phrase, so
# the verb matters: we want the issue that CREATES the outline, not the one that runs it.
OUTLINE_HINT = "test case outline"
OUTLINE_VERB = "create"

# Stripped from the body before publishing. OS becomes labels; Backend is not an axis for
# a mobile case (the client key belongs in Preconditions). Config survives only when the
# drafter wrote one, which by house rule means it is exclusive to a form factor.
STRIP_META = ("- **OS:**", "- **Backend:**")


def load_key():
    """.env beside the repo root first, then the environment. Mirrors refresh.py."""
    path = os.path.join(ROOT, ".env")
    if os.path.isfile(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    key = os.environ.get("LINEAR_API_KEY", "").strip()
    if not key:
        sys.exit(f"LINEAR_API_KEY not found.\n"
                 f"  Looked in: {path}\n"
                 f"             and the shell environment\n"
                 f"  Add a line to .env:  LINEAR_API_KEY=lin_api_...\n"
                 f"  See docs/LINEAR-SETUP.md.")
    return key


def gql(query, variables=None):
    key = load_key()
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        API, data=body,
        headers={"Content-Type": "application/json", "Authorization": key},
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as fh:
            out = json.loads(fh.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 418:
            sys.exit("\nHTTP 418 — the proxy blocked this, it never reached Linear.\n"
                     "Add to allowlist.txt on the Mac host, next to filter.py:\n\n"
                     "    POST https://api.linear.app/graphql\n")
        sys.exit(f"HTTP {e.code} from Linear: {e.read().decode()[:400]}")
    if "errors" in out:
        sys.exit("Linear rejected the query:\n  " +
                 "\n  ".join(e.get("message", "?") for e in out["errors"]))
    return out["data"]


# --------------------------------------------------------------------------- parsing

def parse_cases(path):
    """Split 02-cases.md on '## Case:' headings. Same contract validate_cases.py uses.

    `02-cases.md` stays the complete house-format record, because Testmo import needs
    every field. What Linear shows is a presentation of it: OS lifted to labels, Backend
    dropped. One source, one transform per destination — never two copies.
    """
    import re
    text = open(path, encoding="utf-8").read()
    chunks = re.split(r"^##\s+Case:\s*", text, flags=re.M)[1:]
    cases = []
    for chunk in chunks:
        title = chunk.splitlines()[0].strip()
        raw = chunk[len(chunk.splitlines()[0]):].strip()
        os_val, kept = None, []
        for line in raw.splitlines():
            if line.startswith("- **OS:**"):
                os_val = line.split("**OS:**", 1)[1].strip()
            if not line.startswith(STRIP_META):
                kept.append(line)
        cases.append({
            "title": title,
            "body": "\n".join(kept).strip(),
            "labels": OS_LABELS.get(os_val, []),
            "os": os_val,
        })
    return cases


def state_path(ticket):
    return os.path.join(RUNS, ticket, "review-state.json")


def load_state(ticket):
    p = state_path(ticket)
    if os.path.isfile(p):
        return json.load(open(p, encoding="utf-8"))
    return {"ticket": ticket, "parent": None, "cases": {}}


def save_state(ticket, state):
    with open(state_path(ticket), "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
        fh.write("\n")


# --------------------------------------------------------------------------- lookups

Q_VIEWER = "{ viewer { id name } }"

Q_TICKET = """
query($id: String!) { issue(id: $id) { identifier title labels { nodes { name } } } }"""

Q_PARENT = """
query($id: String!) {
  issue(id: $id) {
    id identifier title
    team { id key states { nodes { id name type } } }
    children { nodes { id identifier title state { name } } }
  }
}"""

Q_CHILDREN = """
query($id: String!) {
  issue(id: $id) {
    children { nodes {
      id identifier title url
      state { name }
      comments { nodes { id body createdAt user { id name } } }
    } }
  }
}"""

M_CREATE = """
mutation($teamId: String!, $parentId: String!, $title: String!, $desc: String!,
         $stateId: String!, $labelIds: [String!]) {
  issueCreate(input: {teamId: $teamId, parentId: $parentId, title: $title,
                      description: $desc, stateId: $stateId, labelIds: $labelIds}) {
    success issue { id identifier url }
  }
}"""

M_UPDATE = """
mutation($id: String!, $title: String!, $desc: String!, $stateId: String!,
         $labelIds: [String!]) {
  issueUpdate(id: $id, input: {title: $title, description: $desc, stateId: $stateId,
                               labelIds: $labelIds}) {
    success issue { id identifier url }
  }
}"""

M_COMMENT = """
mutation($id: String!, $body: String!) {
  commentCreate(input: {issueId: $id, body: $body}) { success comment { id } }
}"""


# Platform labels like `Android` live at the WORKSPACE level, not on the team, so
# `team { labels }` does not return them. This query sees both; team-scoped labels win on
# a name collision because they are the more specific thing to apply.
Q_LABELS = """
query { issueLabels(first: 250) { nodes { id name team { key } } } }"""

Q_OUTLINE = """
query($id: String!) {
  issue(id: $id) { children { nodes { identifier title } } }
}"""


def find_outline(ticket):
    """Find the 'Create a test case outline' sub-issue under the run's ticket."""
    issue = gql(Q_OUTLINE, {"id": ticket})["issue"]
    if not issue:
        return None
    hits = [k for k in issue["children"]["nodes"]
            if OUTLINE_HINT in k["title"].lower()]
    if len(hits) > 1:
        narrowed = [k for k in hits if k["title"].lower().strip().startswith(OUTLINE_VERB)]
        if len(narrowed) == 1:
            other = [h["identifier"] for h in hits if h is not narrowed[0]]
            print(f"  outline sub-issue: {narrowed[0]['identifier']} "
                  f"{narrowed[0]['title']!r}  (not {', '.join(other)})")
            return narrowed[0]["identifier"]
        hits = narrowed or hits
    if len(hits) == 1:
        print(f"  outline sub-issue: {hits[0]['identifier']} {hits[0]['title']!r}")
        return hits[0]["identifier"]
    if len(hits) > 1:
        sys.exit(f"{ticket} has {len(hits)} sub-issues matching {OUTLINE_HINT!r}: "
                 + ", ".join(h["identifier"] for h in hits)
                 + "\n  Name one with --parent.")
    return None


def resolve_states(team):
    by_name = {s["name"]: s["id"] for s in team["states"]["nodes"]}
    if AWAITING not in by_name:
        sys.exit(f"Team {team['key']} has no state named {AWAITING!r}. "
                 f"Has: {sorted(by_name)}")
    return by_name


# --------------------------------------------------------------------------- publish

def publish(ticket, parent_ref, dry=False):
    folder = os.path.join(RUNS, ticket)
    cases_md = os.path.join(folder, "02-cases.md")
    if not os.path.isfile(cases_md):
        sys.exit(f"No {cases_md}")
    cases = parse_cases(cases_md)
    if not cases:
        sys.exit(f"No '## Case:' headings in {cases_md}")

    state = load_state(ticket)
    parent_ref = parent_ref or state.get("parent") or find_outline(ticket)
    if not parent_ref:
        sys.exit(f"No outline sub-issue found under {ticket} and no --parent given.\n"
                 f"  Expected a sub-issue whose title contains {OUTLINE_HINT!r}.\n"
                 f"  Pass one explicitly:  --parent QA-647")

    parent = gql(Q_PARENT, {"id": parent_ref})["issue"]
    if not parent:
        sys.exit(f"No such issue: {parent_ref}")
    states = resolve_states(parent["team"])
    team_id = parent["team"]["id"]
    state["parent"] = parent["identifier"]
    label_ids = {}
    for l in gql(Q_LABELS)["issueLabels"]["nodes"]:
        scoped = (l.get("team") or {}).get("key") == parent["team"]["key"]
        if l["name"] not in label_ids or scoped:
            label_ids[l["name"]] = l["id"]

    # Platform inherited from the run's ticket, e.g. QA-642 -> Android.
    ticket_issue = gql(Q_TICKET, {"id": ticket})["issue"]
    inherited = []
    if ticket_issue:
        inherited = [l["name"] for l in ticket_issue["labels"]["nodes"]
                     if l["name"] in PLATFORM_LABELS]
    if not inherited:
        print(f"  note: {ticket} carries no platform label "
              f"({', '.join(sorted(PLATFORM_LABELS))}) — falling back to each case's OS")

    existing = {c["title"]: c for c in parent["children"]["nodes"]}
    now = datetime.now(timezone.utc).isoformat()
    created, updated, skipped = [], [], []

    if dry:
        print(f"DRY RUN — nothing will be written.\n")
        print(f"parent {parent['identifier']}  {parent['title']!r}")
        print(f"  team {parent['team']['key']}, {len(parent['children']['nodes'])} "
              f"existing sub-issue(s)")
        print(f"  would set every one to {AWAITING!r}")
        if inherited:
            print(f"  platform inherited from {ticket}: {', '.join(inherited)}")
        print()
        for case in cases:
            rec = state["cases"].get(case["title"], {})
            if rec.get("status") == "final":
                verb = "SKIP (final)"
            elif case["title"] in existing:
                verb = f"UPDATE {existing[case['title']]['identifier']}"
            else:
                verb = "CREATE"
            labs = inherited or case["labels"]
            print(f"  {verb:<22} {case['title']}")
            print(f"  {'':<22} labels: {', '.join(labs) or '(none)'} · "
                  f"{len(case['body'])} chars of body")
        print(f"\n  {len(cases)} case(s) total. Re-run without --dry-run to apply.")
        return 0

    # A case renamed in 02-cases.md no longer matches its issue by title. Without this,
    # publish would create a second issue and orphan the first. Positions are stable
    # between a rework and its republish, so fall back to file order for the leftovers.
    unmatched_file = [(i, c) for i, c in enumerate(cases)
                      if c["title"] not in existing]
    titles_in_file = {c["title"] for c in cases}
    orphans = [state["cases"][t] | {"title": t}
               for t in list(state["cases"])
               if t not in titles_in_file and state["cases"][t].get("id")]
    renames = {}
    if len(unmatched_file) == 1 and len(orphans) == 1:
        renames[unmatched_file[0][0]] = orphans[0]
    elif unmatched_file and orphans:
        print(f"  warning: {len(unmatched_file)} new/renamed case(s) and "
              f"{len(orphans)} orphaned issue(s) — too ambiguous to pair safely, "
              f"so these publish as new issues. Check for duplicates.")

    for idx, case in enumerate(cases):
        rec = state["cases"].get(case["title"], {})
        if rec.get("status") == "final":
            skipped.append(case["title"])
            continue
        desc = case["body"]
        names = inherited or case["labels"]
        missing = [n for n in names if n not in label_ids]
        if missing:
            sys.exit(f"Team {parent['team']['key']} has no label(s): {missing}")
        ids = [label_ids[n] for n in names]
        match = existing.get(case["title"]) or renames.get(idx)
        if match:
            iid = match["id"]
            gql(M_UPDATE, {"id": iid, "title": case["title"], "desc": desc,
                           "stateId": states[AWAITING], "labelIds": ids})
            ident = match["identifier"]
            if match["title"] != case["title"]:
                print(f"  renamed {ident}: {match['title']!r}\n"
                      f"       -> {case['title']!r}")
                state["cases"].pop(match["title"], None)
            updated.append(ident)
        else:
            res = gql(M_CREATE, {"teamId": team_id, "parentId": parent["id"],
                                 "title": case["title"], "desc": desc,
                                 "stateId": states[AWAITING], "labelIds": ids})
            issue = res["issueCreate"]["issue"]
            iid, ident = issue["id"], issue["identifier"]
            created.append(ident)
        state["cases"][case["title"]] = {
            "id": iid, "identifier": ident, "status": "awaiting", "synced_at": now,
        }

    save_state(ticket, state)
    print(f"parent {parent['identifier']}  {parent['title']!r}")
    if created: print(f"  created  {len(created)}: {', '.join(created)}")
    if updated: print(f"  updated  {len(updated)}: {', '.join(updated)}")
    if skipped: print(f"  skipped  {len(skipped)} already final")
    print(f"  all set to {AWAITING!r} — awaiting review")
    return 0


# ------------------------------------------------------------------------------ poll

def poll(ticket, write=True, quiet=False):
    state = load_state(ticket)
    if not state.get("parent"):
        sys.exit(f"{ticket} has no published parent. Run publish first.")
    kids = gql(Q_CHILDREN, {"id": state["parent"]})["issue"]["children"]["nodes"]
    by_id = {k["id"]: k for k in kids}

    board, rework, final, nosignal = [], [], [], []
    for title, rec in sorted(state["cases"].items()):
        kid = by_id.get(rec["id"])
        if not kid:
            board.append((title, "MISSING", rec.get("identifier", "?")))
            continue
        name = kid["state"]["name"]
        board.append((title, name, kid["identifier"]))

        if name in FINAL:
            if rec.get("status") != "final":
                rec["status"] = "final"
            final.append((title, kid))
        elif name in DROPPED:
            rec["status"] = "dropped"
        else:
            since = rec.get("synced_at", "")
            notes = [c for c in kid["comments"]["nodes"]
                     if c["createdAt"] > since
                     and not c["body"].lstrip().startswith(BOT_MARK)]
            if notes:
                rec["status"] = "rework"
                rework.append((title, kid, notes))
            elif name in REWORK:
                rec["status"] = "rework-no-instruction"
                nosignal.append((title, kid))
            else:
                rec["status"] = "awaiting"

    if write:
        save_state(ticket, state)
        write_queue(ticket, rework, nosignal, final, board, quiet=quiet)

    tally = {"rework": len(rework), "final": len(final),
             "nosignal": len(nosignal), "total": len(board)}
    tally["done"] = bool(board) and tally["final"] + len(
        [t for t, r in state["cases"].items() if r.get("status") == "dropped"]
    ) == tally["total"]

    if not quiet:
        print(f"{ticket} — parent {state['parent']}")
        width = max((len(t) for t, _, _ in board), default=10)
        for title, name, ident in board:
            mark = {"Done": "OK", "Product Review": "OK"}.get(name, "  ")
            print(f"  {mark} {ident:<9} {title[:width]:<{width}}  {name}")
        print(f"\n  {len(final)} final · {len(rework)} to rework · "
              f"{len(nosignal)} moved with no comment · "
              f"{len(board) - len(final) - len(rework) - len(nosignal)} awaiting")
        if nosignal:
            print("\n  Moved to rework but left no new comment — nothing to act on:")
            for title, kid in nosignal:
                print(f"    {kid['identifier']}  {title}")
        if rework:
            print(f"\n  Wrote runs/{ticket}/06-rework.md — hand it to Claude.")
        if tally["done"]:
            print("\n  ALL CASES APPROVED — the parent can move on.")
    return tally


def write_queue(ticket, rework, nosignal, final, board, quiet=False):
    """Only exists when there is something to act on.

    The watch loop polls every cycle, so writing (and announcing) an empty queue file each
    time buried the real output under pages of 'wrote 06-rework.md'. No rework means no
    file — and a stale one from an earlier cycle is removed rather than left to mislead.
    """
    p = os.path.join(RUNS, ticket, "06-rework.md")
    if not rework and not nosignal:
        if os.path.isfile(p):
            os.remove(p)
            if not quiet:
                print("  no rework outstanding — removed 06-rework.md")
        return
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(f"# {ticket} — rework queue\n\n")
        fh.write(f"Generated by `review_sync.py poll` at {now}. **This file is "
                 f"generated — edit `02-cases.md`, not this.**\n\n")
        fh.write(f"{len(final)} final · {len(rework)} to rework · "
                 f"{len(nosignal)} moved with no comment · {len(board)} total\n\n")
        if not rework:
            fh.write("Nothing to rework.\n")
        for title, kid, notes in rework:
            fh.write(f"---\n\n## {kid['identifier']} — {title}\n\n")
            fh.write(f"{kid['url']}\n\n### Review comments\n\n")
            for c in notes:
                who = (c.get("user") or {}).get("name", "unknown")
                fh.write(f"- **{who}**, {c['createdAt'][:16].replace('T', ' ')}:\n")
                for line in c["body"].strip().splitlines():
                    fh.write(f"  > {line}\n")
                fh.write("\n")
        if nosignal:
            fh.write("---\n\n## Moved to rework with no new comment\n\n")
            fh.write("Nothing to act on — ask before guessing.\n\n")
            for title, kid in nosignal:
                fh.write(f"- {kid['identifier']} — {title}\n")
    if not quiet:
        print(f"  wrote runs/{ticket}/06-rework.md")


# ----------------------------------------------------------------------------- watch

def watch(ticket, interval, on_rework=None, max_cycles=0):
    """Poll until every case is final. Optionally hand rework back to a command.

    `--on-rework` is what makes the whole loop one command: when a case comes back with
    comments, this runs something (in practice `claude -p "/rework <TICKET>"`) that
    revises the cases and republishes, then keeps watching. Without it, watch just
    reports and a human drives the revision.
    """
    print(f"watching {ticket} every {interval}s — ctrl-c to stop")
    if on_rework:
        print(f"  on rework: {on_rework}")
    last, cycles = None, 0
    while True:
        try:
            tally = poll(ticket, write=True, quiet=True)
            state = load_state(ticket)
            snap = {t: r.get("status") for t, r in state["cases"].items()}

            if snap != last:
                stamp = datetime.now().strftime("%H:%M:%S")
                print(f"\n[{stamp}] change detected")
                poll(ticket, write=False)
                last = snap

            if tally["done"]:
                print(f"\n{ticket}: every case is final. Review complete.")
                return 0

            if tally["rework"] and on_rework:
                cycles += 1
                if max_cycles and cycles > max_cycles:
                    print(f"\n  stopping: {max_cycles} rework cycle(s) already run. "
                          f"Re-run watch to continue.")
                    return 2
                stamp = datetime.now().strftime("%H:%M:%S")
                print(f"\n[{stamp}] {tally['rework']} case(s) need rework "
                      f"— cycle {cycles}\n  $ {on_rework}")
                rc = subprocess.call(on_rework, shell=True, cwd=ROOT)
                if rc != 0:
                    print(f"  rework command exited {rc} — stopping so it can be "
                          f"looked at rather than looping on a failure.")
                    return rc
                last = None          # force a fresh report after republishing
                continue             # re-poll immediately, don't sleep

            time.sleep(interval)
        except KeyboardInterrupt:
            print("\nstopped")
            return 0


# Which files mean which stage is done. Order matters — the first missing one is next.
STAGES = [
    ("fetch",    "00-candidates.md", "python3 tools/new_run.py {t} --linear"),
    ("summary",  "01-summary.md",    "/sprint {t}  (resumes at the summary)"),
    ("coverage", "03-coverage.md",   "/sprint {t}  (resumes at coverage)"),
    ("decide",   "04-decision.md",   "/sprint {t}  (resumes at the decision)"),
    ("draft",    "02-cases.md",      "/sprint {t}  (resumes at drafting)"),
    ("proof",    "05-proof.md",      "/sprint {t}  (resumes at proofing)"),
]


def stage(ticket):
    """Say which stage a run is at, so work can resume instead of starting over.

    A run stalls whenever it is waiting on an engineer or product. The run folder is the
    state, so resuming is a matter of reading what is already on disk rather than
    remembering where you were.
    """
    folder = os.path.join(RUNS, ticket)
    if not os.path.isdir(folder):
        print(f"{ticket}: no run folder. Start it:\n"
              f"  ./tools/sprint.sh {ticket}")
        return 10

    def has(name):
        return os.path.isfile(os.path.join(folder, name))

    done = [n for n, f, _ in STAGES if has(f)]
    todo = [(n, f, c) for n, f, c in STAGES if not has(f)]

    print(f"{ticket} — run folder stages")
    for name, f, _ in STAGES:
        print(f"  {'done' if has(f) else '  --'}  {name:<9} {f}")

    qs = os.path.join(folder, "07-questions.md")
    if os.path.isfile(qs):
        open_qs = [l for l in open(qs, encoding="utf-8")
                   if l.strip().startswith("- [ ]")]
        if open_qs:
            print(f"\n  {len(open_qs)} question(s) still unanswered — 07-questions.md:")
            for l in open_qs[:6]:
                print("    " + l.strip()[5:].strip()[:88])

    published = bool(load_state(ticket).get("cases"))
    if published:
        print(f"\n  published — the review loop is where this resumes:")
        print(f"    python3 tools/review_sync.py watch {ticket} --interval 120 \\")
        print(f'        --on-rework "claude -p \'/rework {ticket}\'"')
        return 0
    if todo:
        print(f"\n  next: {todo[0][0]}")
        print("    " + todo[0][2].format(t=ticket))
        return 1
    print(f"\n  drafted but not published:")
    print(f"    python3 tools/review_sync.py publish {ticket}")
    return 2


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    cmd = argv[0]
    rest = [a for a in argv[1:] if not a.startswith("--")]
    ticket = rest[0].strip().upper() if rest else None
    if not ticket:
        sys.exit("Which run? e.g. review_sync.py poll QA-541")

    def opt(flag, default=None):
        return argv[argv.index(flag) + 1] if flag in argv else default

    if cmd == "publish":
        return publish(ticket, opt("--parent"), dry="--dry-run" in argv)
    if cmd == "poll":
        poll(ticket); return 0
    if cmd == "status":
        poll(ticket, write=False); return 0
    if cmd == "stage":
        return stage(ticket)
    if cmd == "watch":
        return watch(ticket, int(opt("--interval", "30")),
                     on_rework=opt("--on-rework"),
                     max_cycles=int(opt("--max-cycles", "0")))
    sys.exit(f"Unknown command {cmd!r}. "
             f"One of: publish, poll, watch, status, stage.")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
