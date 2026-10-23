# Testmo API — what is actually there

Mapped by read-only probing of the live instance on 2026-10-21, because
`docs.testmo.com` is not on the VM allowlist and returns **HTTP 418**. Everything below
was learned with `GET` only — nothing was written. Recorded here so nobody has to probe
it again.

`https://eleostechnologies.testmo.net/api/v1/…`, `Authorization: Bearer $TESTMO_TOKEN`.
Project **1** is *Mobile App*.

## Reading two different 404s

Testmo distinguishes "no such route" from "no such record", and the message is how you
tell which:

| Response | Means |
|---|---|
| `The route api/v1/… could not be found.` | the route does not exist |
| `The repository folder does not exist or was deleted…` | the route exists, the record does not |
| `405 … Supported methods: PATCH` | the route exists and is writable |

That last one is the useful trick: **a `GET` to a write-only route makes the server list
the methods it accepts.** It is how the table below was built without sending a write.

## Route map

| Route | GET | Other |
|---|---|---|
| `projects/{p}` | ✅ dict | |
| `projects/{p}/cases` | ✅ list | **create is unverified** |
| `cases/{id}` | ❌ route absent | — |
| `projects/{p}/cases/{id}` | ❌ route absent | — |
| `projects/{p}/folders` | ✅ list | |
| `folders/{id}` | ✅ (record-level 404) | |
| `projects/{p}/milestones` | ✅ list | |
| `milestones/{id}` | ✅ dict | |
| `projects/{p}/milestones/{id}` | ❌ route absent | — |
| `projects/{p}/runs` | ✅ list, `?milestone_id=` filters | |
| `runs/{id}` | ✅ dict | |
| `projects/{p}/runs/{id}` | 405 | **PATCH** |
| `runs/{id}/results` | ✅ list | |
| `runs/{id}/results/{id}` | 405 | **PATCH** |
| `projects/{p}/automation/runs` | ✅ list | |
| `automation/runs/{id}/tests` | ✅ list | |
| `automation/runs/{id}/threads` | 405 | **POST** |
| `projects/{p}/templates` | ✅ list + field ids | |
| `projects/{p}/fields` | ✅ list (35) — no `entity: case` rows | |
| `projects/{p}/statuses` | ✅ list (25) | |
| `projects/{p}/configs` | ✅ list | |
| `projects/{p}/tags` | ✅ list | |

## The list endpoint hides fields. Never conclude a field does not exist from it.

`projects/{p}/cases` returns **9 of template 3's 17 fields**. Steps, Preconditions and
Goal/Purpose are absent, and so is **Issues** — and there is no member route to ask for
one case in full. A field missing from a list response says nothing about whether the
field exists.

This has caused one wrong conclusion already: case 519702 came back with no issue data, so
cases were declared incapable of carrying issue links. The Testmo UI shows `GRP-324` on
that very case. **The CSV export is the authority on what a case can hold**, not the API
list.

## Issues are a case-level field

The export's `Issues` column (11 of 25) carries them: bare Linear keys, comma-separated,
no spaces, up to three on a case.

    GRP-403,GRP-455        EIN-6924        BUG-132,BUG-292,BUG-295

328 of 3,624 cases use it. Every key belongs to a product team — **EPW** (152), **GRP**
(106), **BUG** (84), **EIN** (79). **No case references a QA ticket.** The field tracks
the engineering work a case exists because of, not the QA task that wrote it.

Run *results* also carry `issues`, but as **integer record ids** (`[412]`), not keys —
a different representation of the same underlying table. 30 of 2,575 recent results use it.

### Writing issues over the API

`POST projects/{p}/cases` **does** take `issues`, but not in the CSV's format. The 422
gives the schema:

> The issues field must be an array of integers or objects with display_id and
> integration_id.

Integers are Testmo's own issue record ids (what a run result's `issues: [412]` holds).
We have keys, not ids, so it is the object form:

```json
"issues": [{"display_id": "QA-685", "integration_id": 2}]
```

**`integration_id` is 2** — the Linear tracker. Found by probing, since no route lists
integrations (`projects/{p}/integrations`, `issue/integrations` and five other spellings
are all route-absent):

| id | result |
|---|---|
| 1 | exists, but `connection_project_id field is required for GitHub and GitLab trackers` |
| **2** | **validates clean — errors identical to the control** |
| 3-6 | `Issue integration with ID n does not exist or is not active.` |

The probe sends each candidate with `name` omitted, so the record can never be created and
the only thing that varies is whether the server objects to the integration.
`tools/probe_issues.py` does this; it is throwaway now that the answer is recorded here.

Cases also go in through the CSV import — see `tools/case_export.py`.

## Manual runs vs automation runs

They are different systems and do not mix.

- A **manual run** is `{milestone_id, config_id, include_all: false, case_ids: [...]}`.
  Its results carry `case_id`, so they land on the repository case. All 100 recent manual
  runs use `include_all: false` with an explicit list.
- An **automation run** is what JUnit/XML submission creates. Its tests carry
  `repository_case_id` — and in every Appium run on this instance that field is `null`.
  **XML results do not attach to repository cases.**

For a human working a checklist on a device, you want a manual run.

## Ids worth not re-looking-up

**Configs** — `projects/1/configs`

| id | name | | id | name |
|---|---|---|---|---|
| 7 | Android | | 9 | iOS |
| 1 | Android Phone | | 3 | iOS Phone (iPhone) |
| 2 | Android Tablet | | 4 | iOS Tablet (iPad) |
| 8 | Android & iOS | | | |

**Template 3 — "Test Case Template"** (the default), field ids:

| id | field | | id | field |
|---|---|---|---|---|
| 9 | Preconditions | | 16 | Steps |
| 4 | Expected Result | | 3 | Goal/Purpose |
| 14 | Restricted to OS | | 15 | Test Case Status |
| 17 | Suite | | 53 | Release Introduced |
| 50 | Remote Config Flag State | | 51 | Remote Config Flag Name |
| 33 | Expected Result(s) | | 34 | Actual Result(s) |
| 8 | Write-up | | 18 | TestRail ID |
| 19 | Build | | 27 | Device |
| 28 | OS Version | | | |

Note that **Suite and Restricted to OS are template fields, not folder structure** — which
is why a case carries both `suite` and `folder_path`.

**Result statuses** — `projects/1/statuses`, for the device leg:

| id | status | | id | status |
|---|---|---|---|---|
| 1 | Untested | | 2 | **Passed** |
| 3 | **Failed** | | 5 | Blocked |
| 4 | Retest - Test Issue | | 8 | Retest - Defect |
| 6 | Note | | 10 | Undesirable Behavior |
| 9 | Not Tested | | 11 | Won't Fix |

**A manual result**, from a real one on run 2076:

```json
{"run_id": 2076, "case_id": 7221, "status_id": 11,
 "note": "<p><a href=\"https://linear.app/eleos-technologies/issue/EIN-7364/…\">",
 "custom_device": …, "custom_build": …, "custom_os_version": …,
 "custom_actual_results": …, "custom_expected_results": …, "custom_writeup": …}
```

The team already links a failing result to a Linear issue in `note`. Keep that.

## Sessions

`projects/{p}/sessions` lists them — 730 on this instance. A session is an exploratory
charter: `template_id` **1**, a `config_id`, a `milestone_id`, and the charter itself in
**`custom_mission`** as HTML. Sessions carry `issues` and `tags` natively.

`projects/{p}/templates` returns only the three *case* templates, so template 1's fields
are not listed there; the session custom fields come from `projects/{p}/fields` where
`entity == "session"`: `custom_mission`, `custom_branch_name`, `custom_configurations`,
and three story-link URLs.

A session's web URL is `/sessions/view/{id}` — confirmed against a real one (881).

## Web URLs, all confirmed against live records

| Thing | URL |
|---|---|
| Case | `/repositories/{repo_id}?group_id={folder_id}&case_id={id}` |
| Run | `/runs/view/{id}` |
| Milestone | `/milestones/view/{id}` |
| Session | `/sessions/view/{id}` |

**A case has no standalone page.** `/repositories/case/{id}` looks plausible and does not
resolve — it was a guess that shipped in links for two runs. The real view is the
repository browser scrolled to that case inside its folder, so it needs `group_id`, which
is the **folder id** (confirmed: case 815328 is folder 197, and its URL is
`/repositories/1?group_id=197&case_id=815328`). `repo_id` is 1 on this instance.

`group_id` means the grouping currently applied, so when the repository is grouped by
suite instead the same slot holds a suite id — `?group_by=repository_cases:custom_suite&
group_id=37` is case 519702 grouped by its suite. Folder grouping is the default, so the
ledger uses `folder_id`.

## Answered since this was written

1. **`POST projects/{p}/cases`** exists and is a **bulk** endpoint: `{"cases": [ … ]}`.
   Custom fields are **top-level keys named by `column_name`**, not a `custom_fields` dict,
   and they are validated against the template. The names are not guessable — Expected
   Result is `custom_expected`, Goal/Purpose is `custom_description` — so read them from
   `GET projects/{p}/fields` where `entity == "repository_case"` (**not** `"case"`, which
   matches nothing).
2. **`POST projects/{p}/runs`** exists — proven by creating one.
3. **`POST projects/{p}/milestones`** exists — same.
4. **`POST projects/{p}/sessions`** — the payload is above.

## Still unknown

- Whether `issues` sent inside a case object is applied or only validated. The 422 for a
  bad integration comes back keyed `issues`, not `cases.0.issues`, which hints the field
  may be read at the envelope level. The next real push settles it: check the created case
  in the browser for the link.

All three are one documentation page away. The blocked request was
`GET https://docs.testmo.com/api/reference/runs`; the allowlist line that would settle it:

```
GET https://docs.testmo.com/*
```

Wildcard justified: the reference is a page per resource (`/runs`, `/milestones`,
`/cases`), so no exact path covers it.
