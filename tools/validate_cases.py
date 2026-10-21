#!/usr/bin/env python3
"""
validate_cases.py — mechanical checks on drafted test cases before a human reads them.

Stage B of the Claude Sprint Work loop. Catches the errors that are tedious to spot by
eye and embarrassing to find later: Result markers that don't line up, areas and suites
that don't exist, flag names that don't match the repository, and cases that duplicate
something already in Testmo.

It does NOT judge whether a case is a good test. That is the proofing step and the human
gate. This only checks that a case is well-formed and not already written.

    python3 validate_cases.py <cases.md>
    python3 validate_cases.py <cases.md> --strict    exit 1 on warnings too

Input format — one case per `## Case:` heading:

    ## Case: Title of the case
    - **Area:** Pin
    - **Suite:** App Navigation/Trip Planner (New TBT)
    - **OS:** All (not restricted)
    - **Flag:** use_form_route_options_v2 = True

    ### Preconditions
    - USER: SOMEUSER

    ### Steps
    1. Do the thing (Result 1)

    ### Expected
    Result 1 = The thing happened
"""

import difflib
import json
import math
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)          # repo root: .env, the cache and runs/ live here
CACHE = os.path.join(ROOT, "testmo-cache.json")

VALID_OS = {"All (not restricted)", "Android", "iOS"}
# The strings Testmo actually stores.
VALID_STATUS = {"In Use", "Automated", "Automated - Android", "Automated  -  iOS",
                "Automated on Axle"}
VALID_FLAG_STATE = {"True", "False", "Not Present", "N/A"}

# How the team writes these on paper, mapped to what Testmo stores. The team template
# says "Manual" and "{on/off}"; those are correct English for the same values. Translate
# them rather than rejecting them — a validator that argues about vocabulary is noise.
STATUS_ALIASES = {
    "manual": "In Use", "in use": "In Use",
    "automated": "Automated",
    "automated - android": "Automated - Android", "automated-android": "Automated - Android",
    "automated - ios": "Automated  -  iOS", "automated-ios": "Automated  -  iOS",
    "automated on axle": "Automated on Axle",
}
FLAG_STATE_ALIASES = {
    "on": "True", "true": "True", "enabled": "True", "yes": "True",
    "off": "False", "false": "False", "disabled": "False", "no": "False",
    "not present": "Not Present", "absent": "Not Present", "removed": "Not Present",
    "n/a": "N/A", "na": "N/A",
}
# From the corpus: median 6 steps, p90 13. Beyond ~15 a case is usually two cases.
STEP_SOFT_MAX = 15
TITLE_SOFT_MAX = 115


def load_corpus():
    if not os.path.isfile(CACHE):
        sys.exit(f"No {CACHE}. Run refresh.py first — validation needs the corpus.")
    data = json.load(open(CACHE, encoding="utf-8"))
    globals()["_CACHE_DATA"] = data
    live = [c for c in data["cases"] if not c["retired"]]
    return {
        "cases": live,
        "areas": {c["area"] for c in live if c["area"]},
        "suites": {c["suite"] for c in live if c["suite"]},
        "flags": {c["flag_name"] for c in live if c["flag_name"]},
        "flag_keys": {c["flag_key"] for c in live if c["flag_key"]},
        "titles": {c["name"]: c for c in live},
        "users": _users(live),
        "rarity": _rarity(live),
        "configs": set(data.get("configs") or []),
    }


def _rarity(live):
    """How informative each title word is: rare words score high, ubiquitous ones ~0."""
    df = Counter()
    for c in live:
        df.update(_keywords(c["name"]))
    n = len(live)
    return {w: max(0.0, math.log(n / k)) for w, k in df.items()}


_KW_STOP = set("""a an the and or but if then to of in on at for from with by as it its
is are was were be been being this that these those should shall will would can could
may might must do does did done have has had not no when while during after before
verify ensure check make test case app user users screen page tap click open close show
shows display displayed new added update change fix issue work works working""".split())


# Phrases that mean the same thing but share no word, and word forms that differ only
# by an ending. Without this, "doesn't force a logout" and "does not log the driver out"
# look unrelated — which is how the closest prior art gets missed.
_PHRASES = [
    (r"\b(?:logged|log|signed|sign)\s*(?:the\s+\w+\s+)?out\b", " logout "),
    (r"\bweb\s*token\b", " token "),
    (r"\bsign\s*[- ]?\s*in\b", " login "),
    (r"\blogged\s*in\b", " login "),
]


def _keywords(title):
    t = title.lower()
    for pat, repl in _PHRASES:
        t = re.sub(pat, repl, t)
    words = set()
    for w in re.findall(r"[a-z][a-z0-9_.]{2,}", t):
        if w in _KW_STOP:
            continue
        words.add(re.sub(r"(?:es|s)$", "", w) if len(w) > 4 else w)
    return words


def _users(live):
    counts = Counter()
    for c in live:
        m = re.search(r"user\s*:\s*([A-Za-z0-9_-]+)", c["preconditions"] or "", re.I)
        if m:
            counts[m.group(1).upper()] += 1
    return counts


def parse(path):
    """Split the markdown into case dicts. Tolerant — reports what it couldn't read."""
    text = open(path, encoding="utf-8").read()
    chunks = re.split(r"^##\s+Case:\s*", text, flags=re.M)[1:]
    cases = []
    for chunk in chunks:
        lines = chunk.splitlines()
        case = {"title": lines[0].strip(), "meta": {}, "raw": chunk, "normalized": {}}
        for key in ("Status", "Area", "Suite", "OS", "Config", "Backend", "Flag",
                    "Release"):
            m = re.search(rf"^\s*[-*]\s*\*\*{key}:\*\*\s*(.+)$", chunk, re.M)
            case["meta"][key] = m.group(1).strip() if m else ""
        # Section ORDER is Title -> Preconditions -> Steps -> Expected Results -> Goals.
        # Parsing stays order-independent so a mis-ordered file still gets its real
        # errors reported, but the order itself is checked below.
        case["order"] = [h.lower() for h in
                         re.findall(r"^###\s+(.+?)\s*$", chunk, re.M)]
        for sec, pattern in (("goals", r"Goals?"),
                             ("preconditions", r"Pre-?conditions"),
                             ("steps", r"Steps"),
                             ("expected", r"Expected(?:\s+Results?)?"),
                             ("assets", r"JSON\s+Assets")):
            m = re.search(rf"^###\s+{pattern}\s*$(.*?)(?=^###\s|\Z)",
                          chunk, re.M | re.S | re.I)
            case[sec] = m.group(1).strip() if m else ""
        cases.append(case)
    return cases


STEP_NUM = re.compile(r"^(\d+)[.)]\s+(.*)$")


def steps_of(block):
    """Steps are NUMBERED — '1. Do the thing'. A tester says "it failed on step 4",
    which only works if the steps have numbers. Preconditions and Expected Results
    stay bulleted.

    Returns (items, numbers, bulleted_count).
    """
    items, numbers, bulleted = [], [], 0
    for line in block.splitlines():
        t = line.strip()
        if not t:
            continue
        m = STEP_NUM.match(t)
        if m:
            numbers.append(int(m.group(1)))
            items.append(m.group(2).strip())
        elif t.startswith(("-", "*")):
            bulleted += 1
            items.append(t[1:].strip())
    return items, numbers, bulleted


def check(case, corpus):
    errors, warnings = [], []
    t = case["title"]

    if not t:
        errors.append("no title")
    elif len(t) > TITLE_SOFT_MAX:
        warnings.append(f"title is {len(t)} chars — long enough to be two cases")

    # --- metadata against the real repository -----------------------------------
    status = case["meta"]["Status"]
    if not status:
        errors.append("no Status")
    elif status not in VALID_STATUS:
        alias = STATUS_ALIASES.get(status.strip().lower())
        if alias:
            case["normalized"]["Status"] = alias
        else:
            near = difflib.get_close_matches(status, VALID_STATUS, n=2, cutoff=0.5)
            errors.append(f"Status {status!r} is not a Testmo value"
                          + (f" — did you mean {near}?" if near else ""))

    # Required on new cases. Most historical cases lack it; that is history, not a
    # standard, and existing cases are not expected to be backfilled.
    release = case["meta"]["Release"]
    if not release:
        errors.append("no Release Introduced — required on new cases")
    elif release.lower() in ("n/a", "na", "-", "?"):
        case["normalized"]["Release"] = "N/A"
    else:
        m = re.search(r"(\d+\.\d+(?:\.\d+)?)", release)
        if not m:
            errors.append(f"Release {release!r} has no version number in it")
        elif m.group(1) != release:
            case["normalized"]["Release"] = m.group(1)

    area = case["meta"]["Area"]
    if not area:
        errors.append("no Area")
    elif area not in corpus["areas"]:
        near = difflib.get_close_matches(area, corpus["areas"], n=3, cutoff=0.6)
        errors.append(f"Area {area!r} is not in the repository"
                      + (f" — did you mean {near}?" if near else ""))

    suite = case["meta"]["Suite"]
    if suite and suite not in corpus["suites"]:
        near = difflib.get_close_matches(suite, corpus["suites"], n=2, cutoff=0.6)
        errors.append(f"Suite {suite!r} is not in the repository"
                      + (f" — did you mean {near}?" if near else ""))

    os_val = case["meta"]["OS"]
    if os_val and os_val not in VALID_OS:
        errors.append(f"OS {os_val!r} must be one of {sorted(VALID_OS)}")

    # Testmo Configurations are a separate axis from "Restricted to OS": OS says where a
    # case MAY run, Config says which device profiles it IS run against. Only 6% of the
    # corpus sets one, so this warns rather than errors — but a wrong value will not
    # import.
    cfg = case["meta"]["Config"]
    if cfg:
        known = corpus["configs"]
        for one in [x.strip() for x in cfg.split(",") if x.strip()]:
            if one not in known:
                near = difflib.get_close_matches(one, known, n=2, cutoff=0.5)
                errors.append(f"Config {one!r} is not a Testmo configuration"
                              + (f" — did you mean {near}?" if near
                                 else f" — defined: {sorted(known)}"))
        if os_val == "Android" and "iOS" in cfg and "Android" not in cfg:
            errors.append("OS is Android but Config names only iOS")
        if os_val == "iOS" and "Android" in cfg and "iOS" not in cfg:
            errors.append("OS is iOS but Config names only Android")
    elif os_val == "All (not restricted)":
        warnings.append("no Config — an unrestricted case runs on every device profile; "
                        "say which ones it is actually meant for")

    flag = case["meta"]["Flag"]
    if flag:
        fname, _, fstate = flag.partition("=")
        fname, fstate = fname.strip(), fstate.strip()
        if fstate and fstate not in VALID_FLAG_STATE:
            alias = FLAG_STATE_ALIASES.get(fstate.strip().strip("{}").lower())
            if alias:
                case["normalized"]["Flag state"] = alias
            else:
                errors.append(f"Flag state {fstate!r} is not a Testmo value — use one "
                              f"of {sorted(VALID_FLAG_STATE)}")
        if fname and fname not in corpus["flags"]:  # noqa: E501
            if fname.lower() in corpus["flag_keys"]:
                errors.append(f"Flag {fname!r} differs only by case from a real flag — "
                              "the repository already has a capitalization split, "
                              "do not add to it")
            else:
                near = difflib.get_close_matches(fname, corpus["flags"], n=2, cutoff=0.5)
                errors.append(f"Flag {fname!r} is not used by any live case"
                              + (f" — did you mean {near}?" if near else ""))

    # --- section order ----------------------------------------------------------
    want = ["pre", "steps", "expected", "goals"]
    seen = [h for h in case.get("order", [])
            if any(h.startswith(w) or w in h for w in want)]
    rank = {"pre": 0, "steps": 1, "expected": 2, "goals": 3}
    got = []
    for h in seen:
        for w, i in rank.items():
            if h.startswith(w) or (w == "expected" and h.startswith("expected")):
                got.append(i)
                break
    if got and got != sorted(got):
        warnings.append("sections are out of order — the house order is "
                        "Preconditions, Steps, Expected Results, Goals")

    # --- backend ----------------------------------------------------------------
    # Testmo has no field for this. It belongs in Preconditions until someone adds a
    # custom field, so the validator only checks it is stated somewhere.
    backend = case["meta"]["Backend"]
    if not backend and not re.search(r"\b(staging|production|prod|qa|reference-qa|"
                                     r"environment|backend|squid)\b",
                                     case["preconditions"], re.I):
        warnings.append("no Backend stated — name the environment, or say "
                        "'any' if it genuinely does not matter")

    # --- goals ------------------------------------------------------------------
    if not case["goals"]:
        warnings.append("no Goals — the template asks what scenario this tests, and "
                        "whether it is smoke or recurring")

    # --- preconditions ----------------------------------------------------------
    if not case["preconditions"]:
        warnings.append("no Preconditions — the template asks for user, setup and "
                        "load definition")
    elif not re.search(r"user\s*:", case["preconditions"], re.I):
        warnings.append("Preconditions name no USER — the template asks for a unique "
                        "user per case")
    else:
        if re.search(r"user\s*:\s*(<[^>]*>|tbd|xxx+|\?+)\s*$",
                     case["preconditions"], re.I | re.M):
            warnings.append("USER is a placeholder — the case cannot be run until an "
                            "account is allocated")
        m = re.search(r"user\s*:\s*([A-Za-z0-9_-]+)\s*$",
                      case["preconditions"], re.I | re.M)
        if m:
            user = m.group(1).upper()
            shared = corpus["users"].get(user, 0)
            if shared >= 20:
                warnings.append(f"USER {user} is already shared by {shared} cases; the "
                                "template asks for a unique user per case")
            if re.fullmatch(r"<.*>|TBD|XXX+", m.group(1), re.I):
                errors.append("USER is a placeholder — a case with an invented or "
                              "unspecified account cannot be run")

    # --- steps and the Result markers -------------------------------------------
    steps, step_nums, bulleted = steps_of(case["steps"])
    if not steps:
        errors.append("no Steps")
    if bulleted:
        errors.append(f"{bulleted} step(s) are bulleted — steps are numbered "
                      "'1.', '2.', '3.' so a tester can say which step failed")
    elif step_nums and step_nums != list(range(1, len(step_nums) + 1)):
        errors.append(f"step numbers are not 1..n in order: {step_nums}")
    if len(steps) > STEP_SOFT_MAX:
        warnings.append(f"{len(steps)} steps; over ~{STEP_SOFT_MAX} usually means "
                        "this is two cases")

    in_steps = [int(n) for n in re.findall(r"\(\s*Result\s*(\d+)\s*\)",
                                           case["steps"], re.I)]
    in_expected = [int(n) for n in re.findall(
        r"^\s*(?:[-*]\s*)?\*{0,2}Result\s*(\d+)\*{0,2}\s*[:=]",
        case["expected"], re.I | re.M)]

    if not case["expected"].strip():
        errors.append("no Expected")
    elif not in_steps and not in_expected:
        # Single-assertion cases are legitimate: a plain sentence, no markers.
        if len(steps) > 6:
            warnings.append(f"{len(steps)} steps but no (Result N) markers — "
                            "a reader will not know where to verify")
    else:
        missing = sorted(set(in_steps) - set(in_expected))
        extra = sorted(set(in_expected) - set(in_steps))
        if missing:
            errors.append(f"Steps mark Result {missing} but Expected never defines "
                          f"{'it' if len(missing) == 1 else 'them'}")
        if extra:
            errors.append(f"Expected defines Result {extra} but no step marks "
                          f"{'it' if len(extra) == 1 else 'them'}")
        dupes = [n for n, c in Counter(in_steps).items() if c > 1]
        if dupes:
            errors.append(f"Result {dupes} marked on more than one step")
        if in_steps and sorted(set(in_steps)) != list(range(1, max(in_steps) + 1)):
            warnings.append(f"Result numbers are not 1..n: {sorted(set(in_steps))}")

    # --- is this already written? -----------------------------------------------
    # Title similarity alone is not enough. "Report Issue button is present in Settings"
    # and "Verify Settings Issue Button is Present" describe the same test and score far
    # below any usable difflib cutoff. So also compare distinguishing words, and weight
    # same-area matches heavily — a near-match inside the area you chose is the one that
    # actually costs you a duplicate in Testmo.
    mine = _keywords(t)
    scored = []
    for name, c in corpus["titles"].items():
        ratio = difflib.SequenceMatcher(None, t.lower(), name.lower()).ratio()
        theirs = _keywords(name)
        shared = mine & theirs
        # Weight shared words by rarity. "rotating" is in 142 titles and means nothing;
        # "webtoken" is in one and means everything.
        weight = sum(corpus["rarity"].get(w, 3.0) for w in shared)
        same_area = (c["area"] or "").lower() == area.lower()
        if ratio >= 0.75 or (weight >= 5 and (same_area or ratio >= 0.35)) or weight >= 9:
            scored.append((weight + ratio * 3 + (3 if same_area else 0), c, name))
    # Keep only matches close to the best one. A long tail of weak hits trains people to
    # skim past the warning that matters.
    scored.sort(key=lambda x: -x[0])
    if scored:
        cutoff = scored[0][0] * 0.6
        for score, c, name in scored[:3]:
            if score < cutoff:
                break
            tag = ("automated" if c["automated"]
                   else "manual" if c["manual"] else c["status"])
            where = ("SAME AREA" if (c["area"] or "").lower() == area.lower()
                     else c["area"])
            warnings.append(
                f"possible duplicate — C{c['key']} [{tag}] ({where}): {name!r}")

    return errors, warnings


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    strict = "--strict" in argv
    if not args:
        print(__doc__)
        return 1
    path = args[0]
    if not os.path.isfile(path):
        sys.exit(f"No such file: {path}")

    corpus = load_corpus()
    cases = parse(path)
    if not cases:
        sys.exit(f"No '## Case:' headings found in {path}.")

    print(f"{len(cases)} case(s) in {os.path.basename(path)}, "
          f"checked against {len(corpus['cases'])} live cases\n")

    n_err = n_warn = 0
    for i, case in enumerate(cases, 1):
        errors, warnings = check(case, corpus)
        n_err += len(errors)
        n_warn += len(warnings)
        mark = "FAIL" if errors else "warn" if warnings else "ok"
        print(f"[{mark:4s}] {i}. {case['title'][:72]}")
        for e in errors:
            print(f"         ERROR  {e}")
        for w in warnings:
            print(f"         warn   {w}")
        for field, value in case["normalized"].items():
            print(f"         →      {field} imports as {value!r}")

    print(f"\n{n_err} error(s), {n_warn} warning(s)")
    if n_err:
        print("Fix the errors before this goes to a human.")
    elif n_warn:
        print("Warnings are judgment calls — read them, then decide.")
    else:
        print("Well-formed. That is not the same as correct — proofing is next.")
    return 1 if (n_err or (strict and n_warn)) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
