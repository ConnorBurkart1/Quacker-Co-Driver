#!/usr/bin/env python3
"""Does POST projects/{p}/cases accept an `issues` field? Creates nothing.

Run this on the Mac — the VM's allowlist is GET-only for Testmo by design, so the
POST is blocked there with HTTP 418 before it leaves the machine.

Every payload below omits `name`, which is required, so the server must reject all of
them. We are reading *which* fields it complains about, not creating a case:

    "Field 'x' is not defined for template_id 3."  -> that spelling is rejected
    a complaint about `name` alone                 -> that spelling was accepted

Throwaway. Delete it once docs/TESTMO-API.md records the answer.
"""
import json, os, sys, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

URL = os.environ.get("TESTMO_URL", "").rstrip("/")
TOK = os.environ.get("TESTMO_TOKEN", "")
if not URL or not TOK:
    sys.exit("TESTMO_URL and TESTMO_TOKEN must be set — see .env.example.")

TICKET = sys.argv[1] if len(sys.argv) > 1 else "QA-642"

# Round 2. The case API accepts `issues`; the 422 told us the shape:
#   "must be an array of integers or objects with display_id and integration_id"
# There is no route that lists integrations (every spelling 404s), so the id is found the
# same way: send it with `name` still missing, so nothing can be created, and watch whether
# the server objects to the integration rather than only to the missing name.
CANDIDATES = [
    ("control — no issues field at all", {}),
    ("bare integer (an existing issue record)", {"issues": [412]}),
]
for _n in range(1, 7):
    CANDIDATES.append(
        (f"object form, integration_id={_n}",
         {"issues": [{"display_id": TICKET, "integration_id": _n}]}))


def probe(label, extra):
    body = {"cases": [dict({"template_id": 3}, **extra)]}
    req = urllib.request.Request(
        f"{URL}/api/v1/projects/1/cases", data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {TOK}", "Accept": "application/json",
                 "Content-Type": "application/json"}, method="POST")
    print(f"--- {label}")
    print(f"    sent  {json.dumps(body)}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            # Should be unreachable: `name` is required.
            print(f"    !!!!  {r.status} A CASE WAS CREATED. Delete it in Testmo.")
            print(f"          {r.read().decode()[:400]}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            msg = json.loads(raw)
            print(f"    {e.code}   {json.dumps(msg.get('errors') or msg)[:300]}")
        except ValueError:
            print(f"    {e.code}   {raw[:300]}")
    except urllib.error.URLError as e:
        print(f"    network: {e}")
    print()


print(f"Probing {URL} with ticket {TICKET}. Nothing should be created.\n")
for label, extra in CANDIDATES:
    probe(label, extra)
print("Read it like this: the control fails ONLY on the missing `name`. Any candidate")
print("whose errors look identical to the control was accepted — that is the integration")
print("id to use. A candidate that draws an extra error about issues/integration is wrong.")
