#!/usr/bin/env python3
"""
coverage.py — query the Testmo case repository export.

Stage A of the Claude Sprint Work loop: answer "what do we already have for this
area, is it still valid, and what's automated?" without loading 6 MB into context.

Usage:
    python3 coverage.py areas [text]        list areas (Folder), optionally filtered
    python3 coverage.py area "<name>"       coverage report for one area
    python3 coverage.py search "<text>"     find cases by text, anywhere
    python3 coverage.py case <id>           one case, in full
    python3 coverage.py health              corpus-wide data quality report

Flags:
    --all        include cases marked "No Longer Valid" (excluded by default)
    --os <os>    restrict to Android / iOS
    --limit <n>  cap results (default 40)
    --full       show steps and expected result in list output
    --titles     one line per case, no marks — cheapest way to scan a whole area
"""

import csv
import html
import math
import os
import re
import sys
from collections import Counter, defaultdict

CSV_NAME = "CLAUDE_LOOK_HERE_FOR_OFFICAL_TEST_CASES.csv"

# This repo is checked out on two machines that mount the share at different paths
# (/home/vm/shared on the VM, ~/Lethal/shared on the Mac), so the export and the cache
# are located relative to this file rather than by absolute path.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)         # repo root: the cache lives here
_CANDIDATES = [
    os.environ.get("TESTMO_EXPORT"),
    os.path.join(_ROOT, "..", "Claude-Context", CSV_NAME),
    os.path.join(_ROOT, CSV_NAME),
    os.path.join(_ROOT, "..", CSV_NAME),
]


def find_csv():
    for c in _CANDIDATES:
        if c and os.path.isfile(c):
            return os.path.normpath(c)
    looked = "\n  ".join(os.path.normpath(c) for c in _CANDIDATES if c)
    sys.exit(
        f"Could not find {CSV_NAME}.\nLooked in:\n  {looked}\n"
        "Set TESTMO_EXPORT=/path/to/the.csv to point at it directly."
    )

# Test Case Status values that mean "this case is automated somewhere"
AUTOMATED_STATUSES = {
    "Automated",
    "Automated - Android",
    "Automated  -  iOS",
    "Automated on Axle",
}
RETIRED_STATUS = "No Longer Valid"
# Only these statuses make a claim about automation. The rest ("No Longer Valid",
# "Pending Review", "Pasta", "Needs Updated") describe validity, not automation,
# so they must not be read as "this is manual" when reconciling the two fields.
# "In Use" is the status that means a human runs this case. It is the authority on
# manual-vs-automated; the Automation column is a secondary signal that disagrees
# with it on 285 cases.
MANUAL_STATUSES = {"In Use"}
# Everything else live is in neither state — drafted, parked, or junk.
UNRUNNABLE_STATUSES = {"Pending Review", "Needs Updated", "Pasta"}


def strip_html(raw):
    """Testmo stores rich text as HTML. Flatten it to readable plain text."""
    if not raw:
        return ""
    if "<" not in raw:
        return raw.strip()
    text = re.sub(r"<li[^>]*>", "\n- ", raw)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"</p>|</div>|</ol>|</ul>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


CACHE = os.path.join(_ROOT, "testmo-cache.json")

SOURCE = {"kind": None, "age": None, "note": ""}


def _from_cache():
    """Prefer the live cache written by refresh.py; fall back to the CSV export."""
    import json
    from datetime import datetime

    data = json.load(open(CACHE, encoding="utf-8"))
    SOURCE["kind"] = "Testmo API"
    SOURCE["age"] = data.get("fetched_at", "")[:16].replace("T", " ") + " UTC"
    SOURCE["note"] = ("Steps/Preconditions merged from the "
                      f"{data.get('export_merged_from')} export")
    rows = []
    for c in data["cases"]:
        rows.append({
            "Case ID": str(c["key"]),
            "Case": c["name"],
            "Folder": c["folder_path"] or c["area"],
            "Suite": c["suite"],
            "Restricted to OS": c["os"],
            "Test Case Status": c["status"],
            "Automation": "Yes" if c["has_automation"] else "No",
            "State": "", "Configurations": "", "Issues": "",
            "Steps": c.get("steps", ""),
            "Expected Result": c.get("expected", ""),
            "Preconditions": c.get("preconditions", ""),
            "Goal/Purpose": c.get("goal", "") or c.get("description", ""),
            "Updated at": c.get("updated_at", "") or "",
            "Updated by": "",
            "_plain": True,
            "_flag_name": c.get("flag_name", ""),
            "_flag_state": c.get("flag_state", ""),
            "_release": c.get("release", ""),
            "_archived": c.get("archived", False),
            "_area": c["area"],
        })
    return rows


def load():
    if os.path.isfile(CACHE):
        rows = _from_cache()
    else:
        csv.field_size_limit(10**7)
        path = find_csv()
        SOURCE["kind"] = "CSV export (stale — run refresh.py)"
        from datetime import datetime
        SOURCE["age"] = datetime.fromtimestamp(os.path.getmtime(path)).date().isoformat()
        with open(path, encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
    for r in rows:
        for k in list(r):
            if isinstance(r[k], str):
                r[k] = r[k].strip()
        r.setdefault("_flag_name", "")
        r.setdefault("_flag_state", "")
        r.setdefault("_release", "")
        r.setdefault("_archived", False)
        r.setdefault("_area", (r.get("Folder") or "").split(" > ")[-1])
        r["_status"] = r["Test Case Status"]
        r["_retired"] = r["_status"] == RETIRED_STATUS
        # Two fields claim to track automation and they disagree on ~285 cases.
        # Keep both and report the disagreement rather than silently picking one.
        by_flag = r["Automation"] == "Yes"
        by_status = r["_status"] in AUTOMATED_STATUSES
        # Status wins. "In Use" means someone runs it by hand, and that is the
        # number that decides how much manual work an area actually costs.
        r["_auto"] = by_status
        r["_manual"] = r["_status"] in MANUAL_STATUSES
        r["_unrunnable"] = not r["_retired"] and not by_status and not r["_manual"]
        status_speaks = by_status or r["_manual"]
        r["_auto_disputed"] = status_speaks and (by_flag != by_status)
    return rows


def visible(rows, args):
    out = rows if args["all"] else [r for r in rows if not r["_retired"]]
    if args["os"]:
        want = args["os"].lower()
        out = [
            r
            for r in out
            if r["Restricted to OS"].lower() in (want, "all (not restricted)", "")
        ]
    return out


def fmt_case(r, full=False):
    marks = []
    if r["_auto"]:
        marks.append("auto*" if r["_auto_disputed"] else "auto")
    elif r["_manual"]:
        marks.append("manual*" if r["_auto_disputed"] else "manual")
    else:
        marks.append(r["_status"] or "no status")
    if r["_retired"]:
        marks.append("RETIRED")
    if r["Restricted to OS"] not in ("All (not restricted)", ""):
        marks.append(r["Restricted to OS"])
    head = f"  C{r['Case ID']:<6} [{', '.join(marks)}] {r['Case']}"
    if not full:
        return head
    body = []
    for label, key in (
        ("Preconditions", "Preconditions"),
        ("Steps", "Steps"),
        ("Expected", "Expected Result"),
    ):
        val = strip_html(r[key])
        if val:
            body.append(f"      {label}: " + val.replace("\n", "\n        "))
    return head + "\n" + "\n".join(body)


def cmd_areas(rows, args, term=None):
    counts = Counter()
    autos = Counter()
    manuals = Counter()
    for r in visible(rows, args):
        f = r["_area"] or "(no folder)"
        if term and term.lower() not in f.lower():
            continue
        counts[f] += 1
        if r["_auto"]:
            autos[f] += 1
        if r["_manual"]:
            manuals[f] += 1
    if not counts:
        print(f"No areas matching {term!r}.")
        return
    print(f"{len(counts)} areas" + (f" matching {term!r}" if term else "") + "\n")
    print(f"{'total':>6} {'auto':>6} {'manual':>7}  area")
    for f, n in counts.most_common(args["limit"]):
        print(f"{n:6d} {autos[f]:6d} {manuals[f]:7d}  {f}")
    t, a, m = sum(counts.values()), sum(autos.values()), sum(manuals.values())
    print(f"{'-'*6} {'-'*6} {'-'*7}")
    print(f"{t:6d} {a:6d} {m:7d}  TOTAL across {len(counts)} area(s)")
    if len(counts) > args["limit"]:
        print(f"\n… {len(counts) - args['limit']} more. Narrow with a search term.")


def cmd_area(rows, args, name):
    n = name.lower()
    # Folder is a full path now, so a bare substring match on it pulls in every
    # subfolder of any ancestor that happens to contain the term. Match the leaf
    # area name first; only widen to the full path if that finds nothing.
    exact = [r for r in rows if r["_area"].lower() == n]
    leaf = [r for r in rows if n in r["_area"].lower()]
    sel = exact or leaf or [r for r in rows if n in (r["Folder"] or "").lower()]
    if not sel:
        print(f"No area matching {name!r}. Try: coverage.py areas {name}")
        return
    scope = ("exact area name" if exact else
             "area name contains" if leaf else "anywhere in the folder path")
    folders = sorted({r["Folder"] for r in sel})
    live = [r for r in visible(sel, args)]
    retired = [r for r in sel if r["_retired"]]

    print(f"AREA: {name!r} → {len(folders)} folder(s), matched on {scope}")
    for f in folders[:8]:
        print(f"  {f}")
    if len(folders) > 8:
        print(f"  … and {len(folders) - 8} more")
    print(f"{len(live)} live cases, {len(retired)} marked '{RETIRED_STATUS}'"
          + (" (shown)" if args["all"] else " (hidden — use --all)"))

    suites = Counter(r["Suite"] for r in live)
    if len(suites) > 1:
        print("\nSUITES — the same area appears under several suite names. These are")
        print("usually iterations of the same feature, not separate areas:")
        for s, n in suites.most_common():
            print(f"  {n:4d}  {s}")

    auto = [r for r in live if r["_auto"]]
    manual = [r for r in live if r["_manual"]]
    unrunnable = [r for r in live if r["_unrunnable"]]
    disputed = [r for r in live if r["_auto_disputed"]]
    os_counts = Counter(r["Restricted to OS"] for r in live)

    print(f"\nCOVERAGE: {len(live)} live cases")
    print(f"  {len(auto):4d}  automated")
    print(f"  {len(manual):4d}  manual (In Use)   ← run by hand")
    if unrunnable:
        print(f"  {len(unrunnable):4d}  neither — not in a runnable state:")
        for st, n in Counter(r["_status"] or "(no status)" for r in unrunnable).most_common():
            print(f"        {n:4d}  {st}")
    if retired:
        print(f"  {len(retired):4d}  retired (excluded above)")
    if disputed:
        print(f"\n  ⚠ {len(disputed)} case(s): the Automation column disagrees with the")
        print("    status. Status is used above; these print with a * below.")
    print("\nOS: " + ", ".join(f"{v or '(blank)'}={n}" for v, n in os_counts.most_common()))

    flags = Counter(
        f"{r['_flag_name']} = {r['_flag_state'] or '?'}"
        for r in live
        if r["_flag_name"] and r["_flag_name"].lower() not in ("n/a", "")
    )
    if flags:
        print("\nREMOTE CONFIG FLAGS named by cases in this area:")
        for v, n in flags.most_common(6):
            print(f"  {n:4d}  {v}")
        print("  Confirm the live flag state before running these.")
    stray = [r for r in live if r["_archived"]]
    if stray:
        print(f"\n⚠ {len(stray)} of these sit under Archive/ but are not marked retired.")

    print(f"\nCASES ({min(len(live), args['limit'])} of {len(live)}):")
    for r in sorted(live, key=lambda x: x["Case"])[: args["limit"]]:
        if args.get("titles"):
            tag = ("auto" if r["_auto"] else "manual" if r["_manual"] else r["_status"])
            print(f"  C{r['Case ID']:<8} [{tag}] {r['Case']}")
        else:
            print(fmt_case(r, args["full"]))
    if len(live) > args["limit"]:
        print(f"\n… {len(live) - args['limit']} more. Raise with --limit.")

    if retired and not args["all"]:
        print(f"\nRETIRED ({len(retired)}) — excluded from the counts above:")
        for r in retired[:10]:
            print(fmt_case(r))
        if len(retired) > 10:
            print(f"  … {len(retired) - 10} more")


def cmd_search(rows, args, term):
    t = term.lower()
    fields = ("Case", "Steps", "Expected Result", "Goal/Purpose", "Preconditions", "Folder")
    hits = [r for r in visible(rows, args) if any(t in r[f].lower() for f in fields)]
    if not hits:
        print(f"No cases matching {term!r}.")
        return
    by_area = defaultdict(list)
    for r in hits:
        by_area[r["Folder"] or "(no folder)"].append(r)
    print(f"{len(hits)} cases matching {term!r}, across {len(by_area)} areas\n")
    shown = 0
    for area, group in sorted(by_area.items(), key=lambda kv: -len(kv[1])):
        if shown >= args["limit"]:
            break
        print(f"{area}  ({len(group)})")
        for r in group[: max(1, args["limit"] - shown)]:
            print(fmt_case(r, args["full"]))
            shown += 1
        print()


def cmd_case(rows, args, case_id):
    key = case_id.lstrip("Cc")
    sel = [r for r in rows if r["Case ID"] == key]
    if not sel:
        print(f"No case with ID {case_id!r}.")
        return
    r = sel[0]
    print(f"C{r['Case ID']}  {r['Case']}")
    print(f"Suite:   {r['Suite']}")
    print(f"Folder:  {r['Folder']}")
    print(f"Status:  {r['_status']}   State: {r['State']}   OS: {r['Restricted to OS']}")
    auto = "yes" if r["_auto"] else "no"
    if r["_auto_disputed"]:
        auto += f"  ⚠ disputed (Automation={r['Automation']}, Status={r['_status']})"
    print(f"Auto:    {auto}")
    if r["Configurations"]:
        print(f"Config:  {r['Configurations']}")
    if r["Issues"]:
        print(f"Issues:  {r['Issues']}")
    print(f"Updated: {r['Updated at']}  by {r['Updated by']}")
    for label, k in (("GOAL", "Goal/Purpose"), ("PRECONDITIONS", "Preconditions"),
                     ("STEPS", "Steps"), ("EXPECTED RESULT", "Expected Result")):
        v = strip_html(r[k])
        if v:
            print(f"\n{label}\n{v}")


STOPWORDS = set("""
a an the and or but if then than that this these those is are was were be been being
to of in on at for from with without by as it its into about over under after before
we you they he she i me my our your their there here when while during up down out off
should shall will would can could may might must do does did done have has had not no
nor so such only own same too very just also any each few more most other some only
test tests testing case cases app application user users verify ensure check make made
new add added update updated change changed fix fixed issue ticket work works working
feature screen page button tap click open close show shows display displayed
""".split())


def tokenize(text):
    words = re.findall(r"[a-z][a-z0-9_]{2,}", (text or "").lower())
    return [w for w in words if w not in STOPWORDS]


def ticket_text(path):
    """Pull just the ticket out of a summary file.

    A run folder's 01-summary.md is mostly scaffolding — field labels like "Remote
    config flag", "Risk", "Open questions". Scoring those matches the template against
    the repository instead of the ticket, which quietly ruins the ranking.
    """
    raw = open(path, encoding="utf-8").read()
    m = re.search(r"^##\s+The ticket\s*$(.*?)(?=^##\s|\Z)", raw, re.M | re.S)
    body = m.group(1) if m else raw
    lines = []
    for line in body.splitlines():
        t = line.strip()
        if not t or t.startswith("#") or t.startswith("|"):
            continue
        if t.startswith("<") and t.endswith(">"):     # unfilled placeholder
            continue
        t = re.sub(r"\*\*.*?:\*\*", " ", t)          # bolded field labels
        t = re.sub(r"^[-*]\s*", "", t)
        if t.strip():
            lines.append(t)
    return "\n".join(lines)


def cmd_suggest(rows, args, text):
    """Rank areas by how well they match free text — a ticket, AC, or notes.

    Mechanical scoring only. Which candidate actually matters is a judgment call for
    whoever reads this; the point is to make that call from evidence instead of from a
    guess at a folder name.
    """
    terms = set(tokenize(text))
    if not terms:
        print("No usable terms in that text.")
        return
    live = visible(rows, args)

    # Weight each term by how rare it is across areas. Without this, "stop" and "trip"
    # — which appear almost everywhere — bury the term that actually identifies the
    # area, and the biggest areas always win on volume rather than relevance.
    areas_all = {(r["_area"] or "(no folder)") for r in live}
    area_terms = defaultdict(set)
    for r in live:
        blob = " ".join([r["_area"] or "", r["Folder"] or "", r["Case"],
                         r.get("Goal/Purpose", "") or ""])
        area_terms[r["_area"] or "(no folder)"].update(tokenize(blob))
    idf = {}
    for t in terms:
        n = sum(1 for a in areas_all if t in area_terms[a]) or 1
        idf[t] = math.log(len(areas_all) / n) + 0.25

    # Score on the BEST evidence per term, not on how often a term recurs. An area whose
    # name is the term should beat an area that merely mentions it in 90 step bodies —
    # otherwise the largest areas win every query by repetition.
    best = defaultdict(dict)      # area -> term -> strongest weight seen
    hits = defaultdict(Counter)
    matched = defaultdict(set)

    for r in live:
        area = r["_area"] or "(no folder)"
        fields = (
            (r["_area"] + " " + (r["Folder"] or ""), 10),
            (r["Case"], 4),
            (r.get("Goal/Purpose", ""), 1.5),
            (r["Steps"] + " " + r["Expected Result"] + " " + r["Preconditions"], 1),
        )
        for blob, weight in fields:
            found = terms.intersection(tokenize(blob))
            for t in found:
                if weight > best[area].get(t, 0):
                    best[area][t] = weight
            if found and weight >= 4:
                matched[area].add(r["Case ID"])

    scores = Counter()
    for area, tw in best.items():
        for t, w in tw.items():
            scores[area] += w * idf[t]
            hits[area][t] = w * idf[t]

    if not scores:
        print(f"Nothing in the repository matches: {', '.join(sorted(terms))}")
        return

    strong = sorted((t for t in terms if idf[t] > 1.5), key=lambda t: -idf[t])[:8]
    print(f"Distinguishing terms: {', '.join(strong) or '(none — text is too generic)'}")
    print(f"All terms: {', '.join(sorted(terms))}\n")
    print("Candidate areas, best first. These are scored, not chosen —")
    print("read the evidence and decide which the ticket actually touches.\n")
    print(f"{'score':>7} {'cases':>6} {'manual':>7}  area")
    for area, sc in scores.most_common(args["limit"] if args["limit"] < 40 else 12):
        in_area = [r for r in live if (r["_area"] or "(no folder)") == area]
        man = sum(1 for r in in_area if r["_manual"])
        top = ", ".join(t for t, _ in hits[area].most_common(4))
        print(f"{sc:7.0f} {len(in_area):6d} {man:7d}  {area}")
        print(f"{'':15s}  matched on: {top}")
        ex = sorted(matched[area])[:2]
        for cid in ex:
            case = next(r for r in in_area if r["Case ID"] == cid)
            print(f"{'':15s}  e.g. C{cid} {case['Case'][:62]}")


def cmd_health(rows, args):
    total = len(rows)
    retired = [r for r in rows if r["_retired"]]
    disputed = [r for r in rows if r["_auto_disputed"]]
    print(f"CORPUS: {total} cases\n")
    print(f"Retired ('{RETIRED_STATUS}'): {len(retired)} ({len(retired)*100//total}%)")
    print(f"  of which marked automated: {sum(1 for r in retired if r['_auto'])}")
    print(f"    → automated tests may still be running against retired cases.\n")
    print(f"Automation fields disagree: {len(disputed)} cases")
    for (a, s), n in Counter((r["Automation"], r["_status"]) for r in disputed).most_common():
        print(f"  {n:5d}  Automation={a:4s}  Test Case Status={s}")
    print()
    suites = defaultdict(set)
    for r in rows:
        for f in [r["Folder"]]:
            if f:
                suites[f].add(r["Suite"])
    multi = {f: s for f, s in suites.items() if len(s) > 1}
    print(f"Folders spanning multiple suites: {len(multi)} of {len(suites)}")
    print("  (same area, different suite name — usually feature iterations)")
    for f, s in sorted(multi.items(), key=lambda kv: -len(kv[1]))[:8]:
        print(f"  {len(s)}  {f}")
    print()
    blank_steps = sum(1 for r in rows if not strip_html(r["Steps"]))
    blank_exp = sum(1 for r in rows if not strip_html(r["Expected Result"]))
    print(f"Cases with no Steps: {blank_steps}")
    print(f"Cases with no Expected Result: {blank_exp}")


def main(argv):
    args = {"all": False, "os": None, "limit": 40, "full": False, "titles": False}
    rest = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--all":
            args["all"] = True
        elif a == "--full":
            args["full"] = True
        elif a == "--titles":
            args["titles"] = True
        elif a == "--os":
            i += 1
            args["os"] = argv[i]
        elif a == "--limit":
            i += 1
            args["limit"] = int(argv[i])
        else:
            rest.append(a)
        i += 1

    if not rest:
        print(__doc__)
        return 1

    rows = load()
    print(f"[source: {SOURCE['kind']} · {SOURCE['age']}"
          + (f" · {SOURCE['note']}" if SOURCE["note"] else "") + "]\n")
    cmd, params = rest[0], rest[1:]
    if cmd == "areas":
        cmd_areas(rows, args, params[0] if params else None)
    elif cmd == "area" and params:
        cmd_area(rows, args, params[0])
    elif cmd == "suggest" and params:
        cmd_suggest(rows, args, " ".join(params))
    elif cmd == "suggest-file" and params:
        cmd_suggest(rows, args, ticket_text(params[0]))
    elif cmd == "search" and params:
        cmd_search(rows, args, params[0])
    elif cmd == "case" and params:
        cmd_case(rows, args, params[0])
    elif cmd == "health":
        cmd_health(rows, args)
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
