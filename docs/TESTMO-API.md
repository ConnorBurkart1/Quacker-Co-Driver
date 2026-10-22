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

**Cases are list-only.** No member read, no member update. Combined with the list endpoint
omitting Steps, Preconditions and Goal/Purpose, assume the repository is not writable over
this API until the docs say otherwise. Cases go in through the CSV import — see
`tools/case_export.py`.

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

## Still unknown

1. **Does `POST projects/{p}/cases` exist, and what body does it take?** The template field
   ids above are almost certainly the payload, but the envelope — `custom_fields` keyed by
   id, versus `custom_<system_name>` columns — is a guess, and guessing at a write API is
   how you create 5 broken cases.
2. **Does `POST projects/{p}/runs` exist?** `PATCH` on the member route is confirmed, so
   runs are writable, but create is not proven.
3. **Does `POST projects/{p}/milestones` exist?**

All three are one documentation page away. The blocked request was
`GET https://docs.testmo.com/api/reference/runs`; the allowlist line that would settle it:

```
GET https://docs.testmo.com/*
```

Wildcard justified: the reference is a page per resource (`/runs`, `/milestones`,
`/cases`), so no exact path covers it.
