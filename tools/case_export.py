#!/usr/bin/env python3
"""
case_export.py — turn drafted cases into a Testmo import file, then learn their ids back.

Testmo's case API is list-only: there is no `cases/{id}` route, no member update, and the
list endpoint returns 9 of template 3's 17 fields — Steps, Preconditions and Goal/Purpose
are not among them. A case without steps is not a test case, so cases do not go in over
the API. They go in through Testmo's CSV import, which is the only path that carries the
fields that matter, and which a human runs in the browser.

That suits the design: nothing here writes to Testmo at all.

    python3 tools/case_export.py build QA-642     -> runs/QA-642/08-import.csv
    …import it in Testmo, then:
    python3 tools/refresh.py
    python3 tools/case_export.py adopt QA-642     -> matches titles to new ids, records them

`adopt` is how the loop learns what the import created. It matches on exact case title,
records every id in the cleanup ledger, and refuses to guess when a title is ambiguous.

Column names come from the live export
(`../Claude-Context/CLAUDE_LOOK_HERE_FOR_OFFICAL_TEST_CASES.csv`), which is the shape
Testmo itself produces. `Case ID` is deliberately omitted — blank means create.
"""

import argparse
import csv
import html
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

import ledger
from review_state import drop_rejected

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "testmo-cache.json")

COLUMNS = ["Case", "Folder", "Suite", "Restricted to OS", "Test Case Status",
           "Template", "Configurations", "Preconditions", "Steps", "Expected Result",
           "Goal/Purpose", "Issues"]

# Testmo links a case to tracker issues through the export's `Issues` column: bare keys,
# comma-separated, no spaces. 328 of the repository's 3,624 cases carry one. The field is
# invisible to GET projects/{p}/cases, which returns 9 of 17 fields — the CSV export is
# the only thing that shows what a case really holds. See docs/TESTMO-API.md.
ISSUE_RE = re.compile(r"[A-Z][A-Z0-9]{1,5}-\d+")

# Over the API, `issues` is NOT the CSV's comma-separated string. The 422 spells out the
# shape: "an array of integers or objects with display_id and integration_id". Integers are
# Testmo's own issue record ids, which we do not have — we have keys — so it is the object
# form. The integration id was found by probing (tools/probe_issues.py): 1 is a GitHub or
# GitLab tracker and demands connection_project_id, 3-6 "do not exist or are not active",
# and 2 validates clean. 2 is the Linear tracker.
ISSUE_INTEGRATION_ID = 2


def issue_keys(*sources):
    """Normalise issue references into Testmo's format, in first-seen order."""
    out = []
    for s in sources:
        for key in ISSUE_RE.findall((s or "").upper()):
            if key not in out:
                out.append(key)
    return ",".join(out)

TEMPLATE = "Test Case Template"
TEMPLATE_ID = 3

# Custom fields are TOP-LEVEL keys on the case object, named by their column_name, and
# validated against the template: a key the template does not define is rejected with
# "Field 'x' is not defined for template_id 3." The names are NOT guessable — Expected
# Result is `custom_expected` and Goal/Purpose is `custom_description` — so they are read
# live from GET projects/{p}/fields, where the entity is `repository_case` (not `case`).
PUSH_FIELDS = ("Preconditions", "Steps", "Expected Result", "Goal/Purpose",
               "Restricted to OS", "Test Case Status", "Suite", "Release Introduced")

# A case Claude drafted imports as this, not as "In Use" — see validate_cases.py.
DRAFT_STATUS = "Claude - Needs Review"

# The team writes "Manual"; Testmo stores "In Use". Same values, different vocabulary —
# translate rather than reject. Mirrors STATUS_ALIASES in validate_cases.py.
STATUS_ALIASES = {
    "claude - needs review": DRAFT_STATUS, "claude needs review": DRAFT_STATUS,
    "needs review": DRAFT_STATUS, "draft": DRAFT_STATUS,
    "manual": "In Use", "in use": "In Use",
    "automated": "Automated",
    "automated - android": "Automated - Android",
    "automated - ios": "Automated  -  iOS",
    "automated on axle": "Automated on Axle",
}

VALID_OS = {"All (not restricted)", "Android", "iOS"}


def load_env():
    path = os.path.join(ROOT, ".env")
    if os.path.isfile(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    url = os.environ.get("TESTMO_URL", "").rstrip("/")
    token = os.environ.get("TESTMO_TOKEN", "")
    if not url or not token:
        die("TESTMO_URL and TESTMO_TOKEN must be set — see .env.example.")
    return url, token


def case_fields(url, token, project):
    """Column names and dropdown options for repository_case fields, read live."""
    def get(path):
        req = urllib.request.Request(f"{url}/api/v1/{path}", headers={
            "Authorization": f"Bearer {token}", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read()).get("result")

    out = {}
    for f in get(f"projects/{project}/fields") or []:
        if f.get("entity") == "repository_case":
            out[f["name"]] = {"id": f["id"], "column": f.get("column_name"),
                              "type": f.get("type"), "options": {}}
    for t in get(f"projects/{project}/templates") or []:
        if t.get("id") != TEMPLATE_ID:
            continue
        for f in t.get("fields", []):
            spec = out.get(f.get("name"))
            if spec and f.get("options"):
                spec["options"] = {o["value"].strip().lower(): o["id"]
                                   for o in f["options"]}
    return out


def folder_candidates(cache, area, suite=""):
    """Every folder an Area could mean, most-populated first.

    Folder names are not unique. 'Form Scan' is two folders — `App Scanning/Imaging >
    Form Scan` (189) and `App Scanning/Imaging (Autoscan) > Form Scan` (38540) — and
    'Settings' is id 197 under App Settings/Logout but 47 under App Drive Axle. Suite does
    not disambiguate them: it is a template field, not folder structure, so the same suite
    appears under both.

    An Area containing '>' is treated as a full folder path and matched as one, which is
    how an ambiguous name is pinned down.
    """
    a, s_ = area.strip().lower(), (suite or "").strip().lower()
    full = ">" in area

    def key(c):
        p = (c.get("folder_path") or "").strip().lower()
        return p if full else (c.get("area") or "").strip().lower()

    def norm(p):
        return re.sub(r"\s*>\s*", " > ", p.strip())

    rows = {}
    for c in cache["cases"]:
        if not c.get("folder_id") or key(c) != (norm(a) if full else a):
            continue
        fid = c["folder_id"]
        r = rows.setdefault(fid, {"id": fid, "path": c.get("folder_path") or "",
                                  "n": 0, "suited": 0})
        r["n"] += 1
        if s_ and (c.get("suite") or "").strip().lower() == s_:
            r["suited"] += 1
    return sorted(rows.values(), key=lambda r: (-r["suited"], -r["n"]))


def folder_id_for(cache, area, suite):
    """The one folder this Area means, or None when it is genuinely ambiguous."""
    cands = folder_candidates(cache, area, suite)
    if len(cands) == 1:
        return cands[0]["id"]
    return None


def die(msg):
    sys.exit(f"case_export.py: {msg}")


# --- markdown -> the HTML Testmo stores -------------------------------------

def inline(text):
    """Escape, then re-apply the two bits of markup the house format uses."""
    t = html.escape(text.strip())
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    return t


def as_paragraphs(items):
    return "".join(f"<p>{inline(i)}</p>" for i in items if i.strip())


def as_list(items):
    return "<ol>" + "".join(f"<li>{inline(i)}</li>" for i in items if i.strip()) + "</ol>"


def collect(block, heading):
    """Items under a `### heading`, joining lines that wrap."""
    m = re.search(rf"^### {re.escape(heading)}\s*$", block, re.M)
    if not m:
        return []
    rest = block[m.end():]
    end = re.search(r"^### |^---\s*$", rest, re.M)
    body = rest[:end.start()] if end else rest

    items, cur, bulleted = [], None, False
    for line in body.splitlines():
        s = line.strip()
        if not s:
            # A blank line ends a prose paragraph. Between bullets it is just spacing.
            if cur is not None and not bulleted:
                items.append(cur)
                cur = None
            continue
        start = re.match(r"^\s*(?:[-*]\s+|\d+[.)]\s+)(.*)$", line)
        if start:
            if cur is not None:
                items.append(cur)
            cur, bulleted = start.group(1).strip(), True
        elif cur is not None:
            cur += " " + s                     # a wrapped continuation line
        else:
            cur, bulleted = s, False           # prose with no bullet, e.g. Goals
    if cur is not None:
        items.append(cur)
    return items


def parse_cases(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    blocks = re.split(r"^## Case:\s*", text, flags=re.M)[1:]
    if not blocks:
        die(f"no '## Case:' headings in {path}")

    out = []
    for b in blocks:
        title = b.splitlines()[0].strip()
        meta = dict(re.findall(r"^- \*\*([^:*]+):\*\*\s*(.+)$", b, re.M))
        get = lambda k: (meta.get(k) or "").strip()

        # No Status line means this came out of drafting, so it is not vetted.
        status_raw = get("Status") or DRAFT_STATUS
        status = STATUS_ALIASES.get(status_raw.lower(), status_raw)
        os_val = get("OS") or "All (not restricted)"

        out.append({
            "title": title,
            "Case": title,
            "Folder": get("Area"),
            "Suite": get("Suite"),
            "Restricted to OS": os_val,
            "Test Case Status": status,
            "Template": TEMPLATE,
            "Configurations": get("Config"),
            "Preconditions": as_paragraphs(collect(b, "Preconditions")),
            "Steps": as_list(collect(b, "Steps")),
            "Expected Result": as_paragraphs(collect(b, "Expected Results")
                                             or collect(b, "Expected")),
            "Goal/Purpose": as_paragraphs(collect(b, "Goals")),
            # Merged with the run's ticket in cmd_build; a case may name extra issues.
            "Issues": issue_keys(get("Issues")),
            "_release": get("Release"),
            "_os_raw": os_val,
        })
    return out


def check(cases):
    warnings = []
    for c in cases:
        if c["Restricted to OS"] not in VALID_OS:
            warnings.append(f"{c['title'][:50]}: OS {c['Restricted to OS']!r} is not one of "
                            + ", ".join(sorted(VALID_OS)))
        for col in ("Folder", "Suite"):
            if not c[col]:
                warnings.append(f"{c['title'][:50]}: {col} is empty")
        if c["Steps"] == "<ol></ol>":
            warnings.append(f"{c['title'][:50]}: no steps parsed")
        if not c["Expected Result"]:
            warnings.append(f"{c['title'][:50]}: no expected results parsed")
        if c["_release"] and c["_release"].upper() not in ("N/A", "NA", ""):
            warnings.append(f"{c['title'][:50]}: Release {c['_release']!r} has no column in "
                            "the import — set Release Introduced in Testmo after import")
    return warnings


# --- commands ---------------------------------------------------------------

def cmd_build(args):
    folder = os.path.join(ROOT, "runs", args.ticket)
    src = os.path.join(folder, "02-cases.md")
    if not os.path.isfile(src):
        die(f"no runs/{args.ticket}/02-cases.md")

    cases = parse_cases(src)
    cases, rejected = drop_rejected(args.ticket, cases)
    for c in cases:
        c["Issues"] = issue_keys(args.ticket, c.get("Issues"))
    warnings = check(cases)
    for t in rejected:
        warnings.insert(0, f"canceled in review, not imported: {t[:70]}")
    if not cases:
        die(f"every drafted case for {args.ticket} was canceled in review — "
            "nothing to import.")
    # A ticket that does not look like a tracker key links nothing. Say so rather than
    # writing a CSV whose Issues column is quietly empty.
    if not issue_keys(args.ticket):
        warnings.insert(0, f"ticket {args.ticket!r} is not a tracker key "
                            "(TEAM-123), so no case will be linked to an issue")
    out = os.path.join(folder, "08-import.csv")
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for c in cases:
            w.writerow(c)

    print(f"{args.ticket} — {len(cases)} case(s) for import\n")
    for c in cases:
        steps = c["Steps"].count("<li>")
        res = c["Expected Result"].count("<p>")
        pre = c["Preconditions"].count("<p>")
        print(f"  {c['title'][:58]:<58} {c['Restricted to OS']:<20} "
              f"{pre} pre / {steps} steps / {res} results")
        print(f"      folder {c['Folder']!r}  suite {c['Suite']!r}  "
              f"status {c['Test Case Status']!r}  issues {c['Issues']!r}")
    if warnings:
        print("\n  warnings:")
        for w_ in warnings:
            print(f"       ! {w_}")

    print(f"\n  wrote runs/{args.ticket}/08-import.csv — nothing was sent to Testmo.")
    print("\n  Next, in the browser: Testmo > the Mobile App repository > Import, map the")
    print("  columns by name, and import. `Case ID` is absent on purpose, so every row is")
    print("  created new. Then:")
    print(f"      python3 tools/case_export.py sync {args.ticket}")
    return 0


def cmd_adopt(args):
    folder = os.path.join(ROOT, "runs", args.ticket)
    src = os.path.join(folder, "02-cases.md")
    if not os.path.isfile(src):
        die(f"no runs/{args.ticket}/02-cases.md")
    if not os.path.isfile(CACHE):
        die("testmo-cache.json is missing — run `python3 tools/refresh.py` first.")

    with open(CACHE, encoding="utf-8") as f:
        cache = json.load(f)
    by_name = {}
    for c in cache["cases"]:
        by_name.setdefault(c["name"].strip().lower(), []).append(c)

    cases = parse_cases(src)
    # A canceled case was never pushed, so it will never be in the cache. Looking for it
    # and exiting 1 on the miss stops the whole run before the milestone and run are made.
    cases, rejected = drop_rejected(args.ticket, cases)
    for t in rejected:
        print(f"  skipping (canceled in review): {t[:66]}")
    found, missing, ambiguous = [], [], []
    for c in cases:
        hits = by_name.get(c["title"].strip().lower(), [])
        if not hits:
            missing.append(c["title"])
        elif len(hits) > 1:
            ambiguous.append((c["title"], [h["id"] for h in hits]))
        else:
            found.append({"id": hits[0]["id"], "name": hits[0]["name"],
                          "area": hits[0].get("area"),
                          "folder_id": hits[0].get("folder_id"),
                          "repo_id": cache.get("repo_id", 1)})

    print(f"{args.ticket} — adopting imported cases "
          f"(cache fetched {cache.get('fetched_at')})\n")
    for f_ in found:
        print(f"  C{f_['id']:<8} {f_['name'][:62]}")
    for t in missing:
        print(f"  --        {t[:62]}  NOT FOUND in the cache")
    for t, ids in ambiguous:
        print(f"  ??        {t[:62]}  matches {len(ids)}: "
              + ", ".join('C' + str(i) for i in ids))

    if found:
        ledger.record(args.ticket, "testmo-case", found, note="created by CSV import")
        print(f"\n  recorded {len(found)} case id(s) in runs/{args.ticket}/CLEANUP.md")
    if missing:
        print(f"\n  {len(missing)} case(s) are not in the cache. Either the import has not "
              "run,\n  or refresh.py has not been run since. Titles must match exactly.")
    if ambiguous:
        print(f"\n  {len(ambiguous)} title(s) match more than one case — refusing to guess. "
              "\n  Resolve the duplicate in Testmo, then re-run adopt.")
    return 1 if (missing or ambiguous) else 0


def cmd_sync(args):
    """Steps 2 and 3 of the import: refresh the cache, then adopt the new ids.

    Step 1 — the CSV import itself — is still a browser action. Everything either side
    of it is scripted, so when the import becomes an API call it drops straight in here
    and the whole sequence becomes one command.
    """
    print("refreshing the cache …")
    rc = subprocess.call([sys.executable, os.path.join(ROOT, "tools", "refresh.py")],
                         cwd=ROOT)
    if rc != 0:
        die(f"refresh.py exited {rc} — the cache was not updated, so adopt would read "
            "stale data. Fix that first.")
    print()
    return cmd_adopt(args)


def cmd_push(args):
    """Create the cases over the API. Proven — C815316 was created this way on QA-685.

    `POST projects/{p}/cases` is a BULK endpoint: the payload is {"cases": [...]}, custom
    fields are top-level keys named by column_name, and `issues` takes objects of
    {display_id, integration_id} rather than the CSV's comma-separated string. See
    docs/TESTMO-API.md. Testmo exposes no member route and no delete, so a case created
    here is removed in the browser — run with --limit 1 when trying something new.
    """
    folder = os.path.join(ROOT, "runs", args.ticket)
    src = os.path.join(folder, "02-cases.md")
    if not os.path.isfile(src):
        die(f"no runs/{args.ticket}/02-cases.md")
    if not os.path.isfile(CACHE):
        die("testmo-cache.json is missing — run `python3 tools/refresh.py` first.")
    with open(CACHE, encoding="utf-8") as f:
        cache = json.load(f)

    cases = parse_cases(src)
    cases, rejected = drop_rejected(args.ticket, cases)
    for t in rejected:
        print(f"  skipping (canceled in review): {t[:66]}")
    if not cases:
        die(f"every drafted case for {args.ticket} was canceled in review — "
            "nothing to push.")
    for c in cases:
        c["Issues"] = issue_keys(args.ticket, c.get("Issues"))
    if args.limit:
        cases = cases[:args.limit]
    url, token = load_env()
    project = cache.get("project_id", 1)
    fields = case_fields(url, token, project)
    if not fields:
        die("could not read repository_case field definitions from the API.")

    print(f"{args.ticket} — pushing {len(cases)} case(s) to the API"
          + ("  (DRY RUN)" if args.dry_run else "")
          + f"  [dropdowns as {args.dropdown}]\n")

    # The endpoint is a BULK create: a 422 on a bare object says
    # "The cases must have at least 1 items." — so every case goes in a `cases` array.
    items = []
    for c in cases:
        fid = folder_id_for(cache, c["Folder"], c["Suite"])
        if not fid:
            cands = folder_candidates(cache, c["Folder"], c["Suite"])
            if not cands:
                die(f"area {c['Folder']!r} matches no folder in the repository.\n"
                    f"  (case: {c['Case'][:60]})")
            lines = [f"      {r['path']}   — {r['n']} cases"
                     + (f", {r['suited']} of them in suite {c['Suite']!r}"
                        if r["suited"] else "")
                     for r in cands]
            die(f"area {c['Folder']!r} is {len(cands)} different folders, so this case "
                f"has nowhere definite to go:\n" + "\n".join(lines) + "\n\n"
                f"  (case: {c['Case'][:60]})\n"
                "  Suite does not disambiguate them — it is a template field, not folder\n"
                "  structure. Set the Area to the full path in 02-cases.md, e.g.\n"
                f"      - **Area:** {cands[0]['path']}")
        payload = {"name": c["Case"], "folder_id": fid, "template_id": TEMPLATE_ID}
        c["Release Introduced"] = c.get("_release") or ""
        for label in PUSH_FIELDS:
            value = c.get(label)
            spec = fields.get(label)
            if not value or not spec or not spec.get("column"):
                continue
            if spec["type"] == "dropdown":
                opt = spec["options"].get(str(value).strip().lower())
                if opt is None:
                    die(f"{label} value {value!r} is not an option on this template.\n"
                        "  valid: " + ", ".join(sorted(spec["options"])))
                payload[spec["column"]] = opt if args.dropdown == "ids" else value
            else:
                payload[spec["column"]] = value

        # The CSV carries issues as "QA-685,EIN-6924"; the API wants them one object each.
        keys = [k.strip() for k in (c.get("Issues") or "").split(",") if k.strip()]
        if keys:
            payload["issues"] = [{"display_id": k,
                                  "integration_id": ISSUE_INTEGRATION_ID} for k in keys]

        c["_folder_id"] = fid
        print(f"  {c['Case'][:66]}  -> folder {fid}"
              + (f"  issues {','.join(keys)}" if keys else "  (no issue link)"))
        items.append(payload)

    envelope = {"cases": items}
    shown = json.dumps(envelope)
    print(f"\n    POST {url}/api/v1/projects/{project}/cases")
    print(f"         {shown[:360]}{'…' if len(shown) > 360 else ''}")
    if args.dry_run:
        print("         (dry run — not sent)")
        return 0

    created = []
    req = urllib.request.Request(
        f"{url}/api/v1/projects/{project}/cases",
        data=json.dumps(envelope).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            res = json.loads(r.read()).get("result")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:1200]
        die(f"POST returned {e.code}.\n\n{detail}\n\n"
            "Nothing was created — this endpoint takes all the cases at once, so a\n"
            "rejection rejects the batch. The error names the fields it wanted; that IS\n"
            "the schema. If it is a dropdown complaining, try --dropdown "
            f"{'values' if args.dropdown == 'ids' else 'ids'}")
    except urllib.error.URLError as e:
        die(f"POST failed to connect: {e.reason}")

    made = res if isinstance(res, list) else [res]
    for item, c in zip(made, cases):
        if isinstance(item, dict) and item.get("id"):
            print(f"         -> created C{item['id']}  {c['Case'][:52]}")
            created.append({"id": item["id"], "name": c["Case"],
                            "folder_id": c.get("_folder_id"),
                            "repo_id": cache.get("repo_id", 1)})

    if created:
        ledger.record(args.ticket, "testmo-case", created, note="created by API push")
        print(f"  recorded {len(created)} case id(s) in runs/{args.ticket}/CLEANUP.md")
        print("\n  If this worked, the browser import step is unnecessary — say so and")
        print("  sprint.sh phase 5 can call this instead of waiting for a human.")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="write the Testmo import CSV from 02-cases.md")
    b.add_argument("ticket")
    b.set_defaults(func=cmd_build)
    a = sub.add_parser("adopt", help="match imported cases back to their new Testmo ids")
    a.add_argument("ticket")
    a.set_defaults(func=cmd_adopt)
    y = sub.add_parser("sync", help="refresh the cache, then adopt — steps 2 and 3 in one")
    y.add_argument("ticket")
    y.set_defaults(func=cmd_sync)
    u = sub.add_parser("push", help="UNPROVEN: try creating the cases over the API")
    u.add_argument("ticket")
    u.add_argument("--dry-run", action="store_true", help="print the request, send nothing")
    u.add_argument("--limit", type=int, help="only push the first N cases (use 1 to probe)")
    u.add_argument("--dropdown", choices=("ids", "values"), default="ids",
                   help="send dropdown fields as option ids (default) or as text")
    u.set_defaults(func=cmd_push)
    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
