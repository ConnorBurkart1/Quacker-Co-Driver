#!/usr/bin/env python3
"""
testmo_run.py — commission a Testmo test run for a ticket, from the run folder.

Stage E0 of the Claude Sprint Work loop: the handoff between a reviewed case outline and
a tester holding a device. It turns `runs/<TICKET>/` into a manifest that names the
milestone, the runs, the configs, and every case id to include.

`plan` reads only local files — the run folder and `testmo-cache.json`. It sends nothing
and needs no token. That is deliberate and it is the whole design: Claude writes the
manifest, a privileged script posts it, and the manifest in between is the audit record
you can read before anything leaves the machine.

    python3 tools/testmo_run.py plan QA-642
    python3 tools/testmo_run.py plan QA-642 --milestone "feature/better-than-bad"

Writes `runs/<TICKET>/09-run.json`.

Where the case ids come from
----------------------------
`04-decision.md` is the source of scope, and only two shapes in it count as "in the pass":

    **Tier 1 — the feature (13):** C18000, C18001*, …      <- a Tier declaration
    | C1832 | App version displayed at the bottom …  |      <- a table row

Everything else is prose. `04-decision.md` deliberately also mentions cases that are NOT
in the pass ("C815193 and C770083–C770093 use Send Diagnostics as a *tool*"), so a regex
over the whole section would silently pull them in. Mentions that are seen and skipped are
recorded in `excluded_mentions` rather than dropped, so the manifest shows its work.

New cases have no Testmo id until they exist in the repository (QA-654). They ride in the
manifest as `new_cases` with `testmo_id: null`; the posting script resolves them after
import and fails if it cannot.
"""

import argparse
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request

import ledger

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "testmo-cache.json")

# Config ids, confirmed live from GET projects/1/configs on 2026-10-21.
CONFIGS = {
    "Android": 7,
    "iOS": 9,
    "Android & iOS": 8,
    "Android Phone": 1,
    "Android Tablet": 2,
    "iOS Phone (iPhone)": 3,
    "iOS Tablet (iPad)": 4,
}

# A case whose OS restriction contradicts the pass platform cannot run on it.
PLATFORM_OS_OK = {
    "Android": {"all (not restricted)", "android", ""},
    "iOS": {"all (not restricted)", "ios", ""},
}

# Statuses worth surfacing on the manifest rather than discovering mid-pass.
STATUS_FLAGS = {
    "No Longer Valid": "retired — should not be in a pass",
    "Needs Updated": "carries a known defect",
    "Pending Review": "not finalised",
}

# Debug marker on everything this loop creates, so a restart can find it all.
MARKER = "Banana"

CASE_RE = re.compile(r"\bC(\d{3,7})\b")
TIER_RE = re.compile(r"^\s*\*\*Tier\b", re.I)
ROW_RE = re.compile(r"^\s*\|\s*C(\d{3,7})\s*\|")


def die(msg):
    sys.exit(f"testmo_run.py: {msg}")


def read(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def load_cache():
    if not os.path.isfile(CACHE):
        die("testmo-cache.json is missing — run `python3 tools/refresh.py` first.")
    with open(CACHE, encoding="utf-8") as f:
        data = json.load(f)
    return data, {str(c["key"]): c for c in data["cases"]}


# --- parsing the run folder -------------------------------------------------

def parse_platform(summary):
    """Platform is the ticket's Linear label. It is never inferred per case."""
    if not summary:
        return []
    m = re.search(r"^- Labels:\s*(.+)$", summary, re.M)
    if not m:
        return []
    labels = [x.strip() for x in m.group(1).split(",") if x.strip()]
    return [x for x in labels if x in ("Android", "iOS")]


def parse_milestone(ticket, summary, override):
    """Always a NEW milestone, never a reused one.

    The base name comes from the ticket's own sub-issue — QA-652 'Create milestone
    feature/better-than-bad' — but a timestamp is appended so every run gets its own.
    Re-running the loop must never append cases to a previous attempt's milestone, and
    while the loop is being debugged each attempt has to be separately deletable.
    """
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H%M")
    if override:
        return override, "--milestone (verbatim, not stamped)"
    base = None
    if summary:
        m = re.search(r"Create milestone ([^'\",]+)", summary)
        if m:
            base = m.group(1).strip()
    src = "sub-issue on the ticket" if base else "ticket id"
    base = base or ticket
    return f"{base} {MARKER} {stamp}".strip(), src


def parse_scope(decision):
    """Case keys in the scoped pass, plus the mentions deliberately left out."""
    if not decision:
        return [], []
    lines = decision.splitlines()
    start = next((i for i, l in enumerate(lines)
                  if l.startswith("## ") and "scoped pass" in l.lower()), None)
    if start is None:
        return [], []
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].startswith("## ")), len(lines))

    keys, excluded = [], []
    in_tier = False
    for line in lines[start + 1:end]:
        if not line.strip():            # a blank line ends the Tier paragraph
            in_tier = False
            continue
        if TIER_RE.match(line):
            in_tier = True
        found = CASE_RE.findall(line)
        if not found:
            continue
        if in_tier:                     # a Tier list wraps; keep taking its continuations
            keys.extend(found)
        elif ROW_RE.match(line):
            keys.append(ROW_RE.match(line).group(1))
        else:
            excluded.append({"text": line.strip()[:120], "cases": found})

    seen, ordered = set(), []
    for k in keys:
        if k not in seen:
            seen.add(k)
            ordered.append(k)
    return ordered, excluded


def parse_new_cases(cases_md):
    """Titles, OS and any Config line from the drafted cases."""
    if not cases_md:
        return []
    out = []
    blocks = re.split(r"^## Case:\s*", cases_md, flags=re.M)[1:]
    for b in blocks:
        title = b.splitlines()[0].strip()
        os_m = re.search(r"^- \*\*OS:\*\*\s*(.+)$", b, re.M)
        cfg_m = re.search(r"^- \*\*Config:\*\*\s*(.+)$", b, re.M)
        out.append({
            "title": title,
            "os": os_m.group(1).strip() if os_m else None,
            "config": cfg_m.group(1).strip() if cfg_m else None,
            "testmo_id": None,
        })
    return out


# --- resolving against the cache --------------------------------------------

def resolve(keys, index, platform):
    """Attach the live cache record to each key. Unrunnable cases are kept, not dropped."""
    resolved, missing = [], []
    ok = PLATFORM_OS_OK.get(platform, set())
    for k in keys:
        c = index.get(k)
        if not c:
            missing.append(k)
            continue
        case_os = (c.get("os") or "").strip()
        runnable = case_os.lower() in ok if ok else True
        rec = {
            "id": c["id"],
            "key": f"C{k}",
            "name": c["name"],
            "area": c.get("area"),
            "suite": c.get("suite"),
            "status": c.get("status"),
            "os": case_os,
            "runnable": runnable,
        }
        if not runnable:
            rec["skip_reason"] = f"OS: {case_os} — cannot run on an {platform} pass"
        if c.get("status") in STATUS_FLAGS:
            rec["flag"] = STATUS_FLAGS[c["status"]]
        resolved.append(rec)
    return resolved, missing


def build(ticket, platform, milestone, milestone_src, cases, missing,
          excluded, new_cases, cache_meta):
    warnings = []
    if missing:
        warnings.append(f"{len(missing)} case(s) in the decision are not in the cache: "
                        + ", ".join("C" + m for m in missing))
    if not milestone:
        warnings.append("No milestone name found — pass --milestone or add a "
                        "'Create milestone <name>' sub-issue to the ticket.")
    if not platform:
        warnings.append("No Android/iOS label on the ticket — no config could be chosen.")
    for c in cases:
        if "flag" in c:
            warnings.append(f"{c['key']} is '{c['status']}' — {c['flag']}")
    pending = [n for n in new_cases if not n.get("testmo_id")]
    if pending:
        warnings.append(f"{len(pending)} new case(s) have no Testmo id yet. Run "
                        "`case_export.py build`, import the CSV, `refresh.py`, then "
                        "`case_export.py adopt` — until then they cannot be in a run.")

    adopted_new = [{"id": n["testmo_id"], "key": f"C{n['testmo_id']}",
                    "name": n["title"], "area": None, "suite": None,
                    "status": "In Use", "os": n.get("os") or "",
                    "runnable": True, "new": True}
                   for n in new_cases if n.get("testmo_id")]
    cases = cases + adopted_new

    runs = []
    for p in platform or []:
        config_name = p
        included = [c for c in cases if c["runnable"]]
        # The cache carries more than one spelling of the same area ("SETTINGS" /
        # "Settings"); fold them so a run isn't named "Settings / SETTINGS".
        areas, seen_area = [], set()
        for c in included:
            a = (c.get("area") or "").strip()
            if a and a.lower() not in seen_area:
                seen_area.add(a.lower())
                areas.append(a.title() if a.isupper() else a)
        runs.append({
            "name": f"{ticket} {' / '.join(areas) if areas else 'scoped pass'} - {config_name}",
            "config_id": CONFIGS.get(config_name),
            "config_name": config_name,
            "include_all": False,
            "case_ids": [c["id"] for c in included],
            "cases": cases,
        })

    return {
        "ticket": ticket,
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
                                 .isoformat(timespec="seconds"),
        "cache_fetched_at": cache_meta.get("fetched_at"),
        "project_id": cache_meta.get("project_id"),
        "milestone": {"name": milestone, "source": milestone_src,
                      "create_new": True},
        "platform": platform,
        "runs": runs,
        "new_cases": new_cases,
        "excluded_mentions": excluded,
        "warnings": warnings,
    }


# --- the one place that writes to Testmo ----------------------------------

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


def post(url, token, path, payload, dry):
    """The only write in this repo's Testmo tooling. Prints what it sends, always."""
    full = f"{url}/api/v1/{path}"
    print(f"    POST {full}")
    body = json.dumps(payload)
    print(f"         {body[:240]}{'…' if len(body) > 240 else ''}")
    if dry:
        print("         (dry run — not sent)")
        return None
    req = urllib.request.Request(full, data=body.encode("utf-8"), method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read()).get("result")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:600]
        die(f"POST {path} returned {e.code}.\n{detail}\n\n"
            "The payload shape above is inferred from the GET responses; the API reference "
            "is behind an allowlist block. If this is a 4xx about fields, the error body is "
            "the schema — paste it and the payload can be corrected.")
    except urllib.error.URLError as e:
        die(f"POST {path} failed to connect: {e.reason}")


def cmd_commission(args):
    """Create the milestone and the runs named in 09-run.json."""
    folder = os.path.join(ROOT, "runs", args.ticket)
    manifest_path = os.path.join(folder, "09-run.json")
    if not os.path.isfile(manifest_path):
        die(f"no runs/{args.ticket}/09-run.json — run `plan` first.")
    with open(manifest_path, encoding="utf-8") as f:
        m = json.load(f)

    pending = [n for n in m["new_cases"] if not n.get("testmo_id")]
    if pending and not args.allow_missing:
        die(f"{len(pending)} new case(s) are not in Testmo yet, so the run would be "
            f"incomplete:\n  " + "\n  ".join(n["title"] for n in pending)
            + "\n\nImport them and run `case_export.py sync "
            + args.ticket + "`, or pass --allow-missing to commission without them.")

    url, token = load_env()
    project = m.get("project_id", 1)
    dry = args.dry_run

    print(f"{args.ticket} — commissioning"
          + ("  (DRY RUN — nothing is sent)" if dry else ""))

    print(f"\n  milestone: {m['milestone']['name']!r}")
    ms = post(url, token, f"projects/{project}/milestones",
              {"name": m["milestone"]["name"]}, dry)
    ms_id = (ms or {}).get("id")
    if ms_id:
        ledger.record(args.ticket, "testmo-milestone",
                      [{"id": ms_id, "name": m["milestone"]["name"]}])

    made = []
    for r in m["runs"]:
        print(f"\n  run: {r['name']!r}  ({len(r['case_ids'])} cases)")
        payload = {"name": r["name"], "config_id": r["config_id"],
                   "include_all": False, "case_ids": r["case_ids"]}
        if ms_id:
            payload["milestone_id"] = ms_id
        res = post(url, token, f"projects/{project}/runs", payload, dry)
        if res and res.get("id"):
            made.append({"id": res["id"], "name": r["name"]})
    if made:
        ledger.record(args.ticket, "testmo-run", made)

    if dry:
        print("\n  dry run — nothing was created.")
        return 0
    print(f"\n  created. Cleanup list — runs/{args.ticket}/CLEANUP.md:")
    print(ledger.summary(args.ticket))
    return 0


# --- commands ---------------------------------------------------------------

def cmd_plan(args):
    folder = os.path.join(ROOT, "runs", args.ticket)
    if not os.path.isdir(folder):
        die(f"no run folder at runs/{args.ticket}/ — start with `new_run.py {args.ticket}`.")

    summary = read(os.path.join(folder, "01-summary.md"))
    decision = read(os.path.join(folder, "04-decision.md"))
    cases_md = read(os.path.join(folder, "02-cases.md"))
    if not decision:
        die(f"runs/{args.ticket}/04-decision.md is missing — there is no scope to plan from.")

    cache_meta, index = load_cache()
    platform = parse_platform(summary)
    milestone, msrc = parse_milestone(args.ticket, summary, args.milestone)
    keys, excluded = parse_scope(decision)
    if not keys:
        die("no scoped-pass cases found in 04-decision.md. Expected a '## The scoped pass' "
            "section with **Tier** lines or a | C#### | table.")

    cases, missing = resolve(keys, index, platform[0] if platform else None)
    new_cases = parse_new_cases(cases_md)

    # case_export.py adopt records the ids the CSV import created. Until that has run,
    # the new cases have no id and cannot be put in a run.
    adopted = {e["name"].strip().lower(): e["id"]
               for e in ledger.load(args.ticket)["entries"]
               if e["kind"] == "testmo-case"}
    for n in new_cases:
        n["testmo_id"] = adopted.get(n["title"].strip().lower())
    manifest = build(args.ticket, platform, milestone, msrc, cases, missing,
                     excluded, new_cases, cache_meta)

    out = os.path.join(folder, "09-run.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")

    # Human summary — the file is the contract, this is just so you can see it at a glance.
    print(f"{args.ticket} — run plan")
    print(f"  milestone   {manifest['milestone']['name'] or '(none)'}"
          f"{'  [' + msrc + ']' if msrc else ''}")
    print(f"  platform    {', '.join(platform) or '(none)'}")
    print(f"  cache       {manifest['cache_fetched_at']}")
    for r in manifest["runs"]:
        print(f"\n  run  {r['name']}")
        print(f"       config {r['config_name']} ({r['config_id']}) · "
              f"{len(r['case_ids'])} case(s) to run")
        for c in r["cases"]:
            mark = "  " if c["runnable"] else "--"
            extra = c.get("skip_reason") or c.get("flag") or ""
            print(f"       {mark} {c['key']:<9} {c['status']:<20} {c['name'][:46]:<46}"
                  f" {extra}")
    pending = [n for n in manifest["new_cases"] if not n.get("testmo_id")]
    if pending:
        print(f"\n  new cases — not yet in Testmo ({len(pending)}):")
        for n in pending:
            print(f"       .. {n['title'][:66]}")
    if excluded:
        print(f"\n  mentioned in the section but not taken as scope ({len(excluded)}):")
        for e in excluded:
            print(f"       -- {', '.join('C' + c for c in e['cases'])}: {e['text'][:70]}")
    if manifest["warnings"]:
        print("\n  warnings:")
        for w in manifest["warnings"]:
            print(f"       ! {w}")
    print(f"\n  wrote runs/{args.ticket}/09-run.json — nothing was sent.")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan", help="build the run manifest from the run folder (sends nothing)")
    p.add_argument("ticket")
    p.add_argument("--milestone",
                   help="exact milestone name to use instead of the generated one")
    p.set_defaults(func=cmd_plan)
    c = sub.add_parser("commission", help="create the milestone and runs in Testmo")
    c.add_argument("ticket")
    c.add_argument("--dry-run", action="store_true",
                   help="print the exact requests without sending them")
    c.add_argument("--allow-missing", action="store_true",
                   help="commission even though some new cases are not in Testmo yet")
    c.set_defaults(func=cmd_commission)
    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
