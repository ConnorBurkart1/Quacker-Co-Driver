#!/usr/bin/env python3
"""
refresh.py — pull the Testmo case repository fresh and normalize it to a local cache.

Stage A of the Claude Sprint Work loop. coverage.py reads the cache this writes, so
queries stay instant and offline; this script is the only part that needs network.

    python3 refresh.py              full pull
    python3 refresh.py --dry-run    show what would be fetched, fetch nothing

Reads TESTMO_URL and TESTMO_TOKEN from .env beside this file, or from the environment.
READ-ONLY: this script issues GET requests only. It must never write to Testmo.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)          # repo root: .env, the cache and runs/ live here
CACHE = os.path.join(ROOT, "testmo-cache.json")
PROJECT_ID = 1  # "Mobile App" — see refresh.py --dry-run for the project list
PER_PAGE = 100
DELAY = 0.15  # courtesy pause between pages

# Status values that mean the case is automated. "In Use" means a human runs it.
AUTOMATED_STATUSES = {"Automated", "Automated - Android", "Automated  -  iOS",
                      "Automated on Axle"}
MANUAL_STATUSES = {"In Use"}
RETIRED_STATUS = "No Longer Valid"

# The cases endpoint returns 9 of template 3's 17 fields. Steps, Preconditions and
# Goal/Purpose are defined on the template but not exposed, and there is no
# single-case endpoint (404). The CSV export does carry them, and joins cleanly on
# API key == CSV "Case ID", so those three fields are merged in from the export and
# tagged with its age. Everything else comes from the API and is live.
EXPORT_CSV = os.path.join(ROOT, "..", "Claude-Context",
                          "CLAUDE_LOOK_HERE_FOR_OFFICAL_TEST_CASES.csv")

FLAG_STATE_CANON = {"not present": "Not Present", "true": "True",
                    "false": "False", "n/a": "N/A", "": ""}


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
        sys.exit("TESTMO_URL and TESTMO_TOKEN must be set (in .env beside this script).")
    if not url.startswith("http"):
        sys.exit(f"TESTMO_URL looks wrong: {url!r} — it needs the https:// scheme.")
    return url, token


def get(url, token, path, params=None):
    """One GET against the Testmo API, with 429 handling. Reads only."""
    qs = ("?" + urllib.parse.urlencode(params)) if params else ""
    full = f"{url}/api/v1/{path}{qs}"
    req = urllib.request.Request(full, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    })
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = int(e.headers.get("Retry-After") or 60)
                print(f"  rate limited; waiting {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            body = e.read()[:400].decode("utf-8", "replace")
            if e.code == 418:
                sys.exit(f"\nPROXY BLOCK on {full}\n"
                         "That URL is not on the allowlist. Add it on the Mac as:\n"
                         f"  GET {full.split('?')[0]}\n")
            sys.exit(f"HTTP {e.code} on {full}\n{body}")
        except urllib.error.URLError as e:
            if attempt == 3:
                sys.exit(f"Connection failed for {full}: {e.reason}")
            time.sleep(2 * (attempt + 1))
    sys.exit(f"Gave up on {full}")


def get_all(url, token, path, params=None, label=""):
    """Page through an endpoint until next_page is null."""
    out, page = [], 1
    while True:
        p = dict(params or {})
        p.update({"page": page, "per_page": PER_PAGE})
        data = get(url, token, path, p)
        result = data.get("result", data if isinstance(data, list) else [])
        out.extend(result)
        last = data.get("last_page") or 1
        if label:
            print(f"\r  {label}: {len(out)} ({page}/{last})", end="", file=sys.stderr)
        if not data.get("next_page"):
            break
        page += 1
        time.sleep(DELAY)
    if label:
        print(file=sys.stderr)
    return out


def strip_html(raw):
    if not raw:
        return ""
    t = re.sub(r"<li[^>]*>", "\n- ", raw)
    t = re.sub(r"<br\s*/?>", "\n", t)
    t = re.sub(r"</p>|</div>|</ol>|</ul>|</tr>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = (t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
          .replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'"))
    return re.sub(r"\n\s*\n+", "\n", t).strip()


def load_export_text():
    """Merge Steps / Preconditions / Goal/Purpose in from the CSV export."""
    import csv
    if not os.path.isfile(EXPORT_CSV):
        return {}, None
    csv.field_size_limit(10**7)
    with open(EXPORT_CSV, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    age = datetime.fromtimestamp(os.path.getmtime(EXPORT_CSV),
                                 timezone.utc).date().isoformat()
    return {r["Case ID"].strip(): r for r in rows if r.get("Case ID")}, age


def name_of(v):
    """Dropdowns arrive as {id, name}; multi-selects as a list of them."""
    if isinstance(v, dict):
        return (v.get("name") or "").strip()
    if isinstance(v, list):
        return ", ".join(name_of(x) for x in v if x)
    return (v or "").strip() if isinstance(v, str) else ""


def folder_paths(folders):
    """Build 'Parent > Child' paths from parent_id. The CSV export flattens this away."""
    by_id = {f["id"]: f for f in folders}
    paths = {}

    def walk(fid, seen=()):
        if fid in paths:
            return paths[fid]
        f = by_id.get(fid)
        if not f or fid in seen:
            return ""
        parent = f.get("parent_id")
        prefix = walk(parent, seen + (fid,)) if parent else ""
        paths[fid] = f"{prefix} > {f['name']}" if prefix else f["name"]
        return paths[fid]

    for fid in by_id:
        walk(fid)
    return paths


def normalize(case, paths, export):
    status = name_of(case.get("custom_test_case_status"))
    automated = status in AUTOMATED_STATUSES
    manual = status in MANUAL_STATUSES
    retired = status == RETIRED_STATUS
    flag_api = bool(case.get("has_automation"))
    path = paths.get(case.get("folder_id"), "")
    ex = export.get(str(case.get("key")), {})
    flag_state = (case.get("custom_remote_config_flag_state") or "").strip()
    flag_name = (case.get("custom_remote_config_flag_name") or "").strip()
    return {
        "id": case.get("id"),
        "key": case.get("key"),
        "name": (case.get("name") or "").strip(),
        "folder_id": case.get("folder_id"),
        "folder_path": path,
        "area": path.split(" > ")[-1] if path else "",
        "suite": name_of(case.get("custom_suite")),
        "status": status,
        "os": name_of(case.get("custom_restricted_to_os")),
        "automated": automated,
        "manual": manual,
        "retired": retired,
        "unrunnable": not (automated or manual or retired),
        # has_automation is the API's own flag; it disagrees with the status field
        # on a few hundred cases, so keep both and report the conflict.
        "has_automation": flag_api,
        "disputed": (automated or manual) and (flag_api != automated),
        # Flag values are hand-typed and inconsistently cased ("Not Present",
        # "not present", "Not present"). Canonicalize for grouping, keep the raw.
        "flag_name": flag_name,
        "flag_key": flag_name.lower(),
        "flag_state": FLAG_STATE_CANON.get(flag_state.lower(), flag_state),
        "archived": path.startswith("Archive"),
        "release": (case.get("custom_release_introduced") or "").strip(),
        "description": strip_html(case.get("custom_description")),
        "expected": strip_html(case.get("custom_expected")),
        # From the export, not the API — see EXPORT_CSV above.
        "steps": strip_html(ex.get("Steps")),
        "preconditions": strip_html(ex.get("Preconditions")),
        "goal": strip_html(ex.get("Goal/Purpose")),
        # Testmo's native Configurations. Exported in the CSV but absent from the cases
        # API response, so it rides in with the other merged fields.
        "configs": (ex.get("Configurations") or "").strip(),
        "updated_at": case.get("updated_at"),
    }


def main(argv):
    url, token = load_env()
    dry = "--dry-run" in argv

    if dry:
        print("Projects visible to this token:")
        for p in get(url, token, "projects").get("result", []):
            mark = " <- PROJECT_ID" if p["id"] == PROJECT_ID else ""
            print(f"  id={p['id']:<3} {p['name']}{mark}")
        counts = get(url, token, f"projects/{PROJECT_ID}/cases",
                     {"page": 1, "per_page": PER_PAGE})
        print(f"\nWould fetch {counts.get('total')} cases "
              f"in {counts.get('last_page')} pages, plus folders and templates.")
        return 0

    print(f"Pulling project {PROJECT_ID} from {url} …", file=sys.stderr)
    configs = get(url, token, f"projects/{PROJECT_ID}/configs").get("result", [])
    folders = get_all(url, token, f"projects/{PROJECT_ID}/folders", label="folders")
    cases_raw = get_all(url, token, f"projects/{PROJECT_ID}/cases", label="cases")

    paths = folder_paths(folders)
    export, export_age = load_export_text()
    if export:
        print(f"  merging Steps/Preconditions from the export ({export_age})",
              file=sys.stderr)
    else:
        print("  WARNING: export CSV not found — cases will have no Steps text",
              file=sys.stderr)
    cases = [normalize(c, paths, export) for c in cases_raw]

    previous = {}
    if os.path.isfile(CACHE):
        try:
            previous = {c["id"]: c["updated_at"]
                        for c in json.load(open(CACHE))["cases"]}
        except Exception:
            previous = {}

    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "instance": url,
        "project_id": PROJECT_ID,
        "export_merged_from": export_age,
        "configs": [c["name"] for c in configs],
        "folders": [{"id": f["id"], "name": f["name"], "parent_id": f.get("parent_id"),
                     "depth": f.get("depth"), "path": paths.get(f["id"], ""),
                     "case_count": f.get("case_count")} for f in folders],
        "cases": cases,
    }
    tmp = CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, CACHE)

    live = [c for c in cases if not c["retired"]]
    print(f"\nWrote {CACHE}")
    print(f"  {len(cases)} cases, {len(folders)} folders, "
          f"max depth {max((f.get('depth') or 0) for f in folders)}")
    print(f"  {len(live)} live  "
          f"({sum(c['automated'] for c in live)} automated, "
          f"{sum(c['manual'] for c in live)} manual, "
          f"{sum(c['unrunnable'] for c in live)} neither)")
    print(f"  {sum(c['retired'] for c in cases)} retired, "
          f"{sum(c['disputed'] for c in cases)} with a disputed automation flag")
    flagged = [c for c in live if c["flag_key"] and c["flag_key"] != "n/a"]
    print(f"  {len(flagged)} live cases name a remote-config flag "
          f"({len({c['flag_key'] for c in flagged})} distinct flags)")
    no_steps = sum(1 for c in live if not c["steps"])
    print(f"  {len(live) - no_steps} live cases have Steps text "
          f"(merged from the {export_age} export); {no_steps} have none")
    withcfg = sum(1 for c in live if c["configs"])
    print(f"  {withcfg} live cases set a Configuration "
          f"(of {len(configs)} defined: {', '.join(c['name'] for c in configs)})")
    stray = [c for c in live if c["archived"]]
    if stray:
        print(f"  ⚠ {len(stray)} live-by-status case(s) sit under Archive/")
    if previous:
        new = [c for c in cases if c["id"] not in previous]
        changed = [c for c in cases
                   if c["id"] in previous and previous[c["id"]] != c["updated_at"]]
        print(f"  since last refresh: {len(new)} new, {len(changed)} updated")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
