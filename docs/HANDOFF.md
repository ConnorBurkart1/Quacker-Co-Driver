# Handoff — state as of 2026-10-21 (Stage C complete, committed)

Written because the sessions that built this repo don't live in it. Read `README.md` first
for what the thing *is*; this file is where it stands, what's half-done, and the traps
that have already cost time.

## The three machines

Almost every "can we do this" question resolves to "on which machine", so assign the
stage to a host before anything else.

| | What it has | What it does |
|---|---|---|
| **The VM** (`/home/vm`) | the repo via the 9p share, an allowlisted proxy, **no device access at all** | **Claude Code runs here.** Reading, generating, cross-referencing, Testmo, Linear |
| **The Mac** (`~/Lethal/shared`) | phones on USB, `adb`, Appium, full network, the *same* checkout | anything touching a device — Stage E, later, in its own Claude session |
| **Mac Mini hub** | ~20 devices, CI runner | Appium regression. Not on demand |

**The one thing that lives on the Mac today is `allowlist.txt`**, next to `filter.py` on
the host. That split has caused real confusion: everything else about setup is a VM thing,
but the allowlist is edited on the host.

The share means `.mcp.json`, `.env` and `runs/` appear on both sides. They only *do*
anything where Claude Code actually runs, which is the VM.

## Where the stages stand

| Stage | State |
|---|---|
| **A — the coverage answer** | **Done.** `tools/refresh.py` + `tools/coverage.py` + the `coverage-check` skill |
| **B — ticket in, cases out** | **Done.** `case-draft` skill, `case-proofer` agent, `validate_cases.py`, run folders. Two practice runs on real old tickets |
| **C — read-only access** | **Done.** Testmo live; Linear connected and all five checks verified 2026-10-21 — see below |
| **D — review view** | **Done differently.** Linear is the review surface — no bespoke UI was built. See below |
| **E — the device leg** | Not started. Runs on the Mac |
| **F — evidence view** | Not started |
| **G — reporting out** | Not started. Write access, one system at a time |

---

# Stage C in detail

It split by system, and the halves needed completely different things.

## Testmo — done

REST API with a token in `.env`, **not** the MCP connector (we were never invited to it).
That turned out to be the better answer: REST puts the verb in the HTTP method, so

```
GET https://eleostechnologies.testmo.net/api/v1/*
```

is **real read-only enforcement at the network boundary**. There is no read-only token tier
in Testmo, so that one allowlist line is the *entire* enforcement. `refresh.py` issues GET
only. **Never add a write method.**

Project 1 is "Mobile App". `refresh.py` writes `testmo-cache.json` (~6.6 MB, git-ignored)
in about 40s. Steps, Preconditions and Goal come from the CSV export, not the API — the API
returns only 9 of template 3's 17 fields — so those three are as old as the last export
(2026-10-13). Everything else is live.

## Linear — connected and verified 2026-10-21

**Two independent locks, both on Linear's side:**

1. **The endpoint** `https://mcp.linear.app/mcp/readonly` only ever exposes read tools.
2. **The credential** — a personal API key restricted to `Read` and to selected teams.

**The proxy is *not* one of the locks here.** MCP over Streamable HTTP sends every JSON-RPC
message as a POST body to a single endpoint — `initialize`, `tools/list` and reading an
issue are all POSTs. The method carries no meaning, so a `POST` line is not a write grant
and a `GET`-only line would block everything. This is the opposite of the Testmo situation
and the two should not be reasoned about the same way.

**Key, not OAuth.** OAuth 2.1 with dynamic client registration wants an interactive browser
the VM doesn't have, plus discovery, registration and token-exchange endpoints allowlisted.
A bearer key needs one line and no browser.

### What's in the repo

`.mcp.json` at the root — committed, holds no secret:

```json
{
  "mcpServers": {
    "linear": {
      "type": "http",
      "url": "https://mcp.linear.app/mcp/readonly",
      "headers": { "Authorization": "Bearer ${LINEAR_API_KEY}" }
    }
  }
}
```

**That file is finished. It never changes and never holds the key.**

### Setup — all three done, confirmed working 2026-10-21

1. `POST https://mcp.linear.app/mcp/readonly` in `allowlist.txt` **on the host**, next to
   `filter.py`.
2. `LINEAR_API_KEY` exported in **the VM's** shell — `~/.bashrc`, not `.env`. `.env` is
   parsed by `refresh.py` in Python; the shell never sees it, and `${LINEAR_API_KEY}` is
   expanded by the shell environment at server load.
3. Claude Code **launched from the repo root**. Project MCP servers are read from
   `.mcp.json` in the working directory.

```bash
echo 'export LINEAR_API_KEY=lin_api_...' >> ~/.bashrc    # once, in the VM
cd /home/vm/shared/Quacker-Co-Driver
claude
```

### Traps already hit — don't repeat these

- **Don't approve the `claude.ai Linear` connector.** It's a different auth path: browser
  OAuth redirecting to `claude.ai/api/mcp/auth_callback`, requesting **Read, Write,**
  Identity and Email against the read-write `https://mcp.linear.app`. Approving it makes
  the whole arrangement above pointless. Leave it on "needs authentication" permanently.
  The 418s seen at `https://mcp.linear.app` (no path) were that connector being blocked —
  the proxy working correctly, not our server failing.
- **Don't paste the key into `.mcp.json`.** It was once pasted as `$lin_api_...`, which
  expanded to nothing *and* put a live secret in a git-tracked file. That key should be
  treated as burned; make a fresh one. `git grep lin_api_` should always return nothing.
- **Don't launch from `/home/vm`.** From there `.mcp.json` doesn't exist as far as Claude
  Code is concerned, `/mcp` shows only the seven claude.ai connectors, and the UI steers
  you toward the OAuth connector — which is how the trap above gets sprung.

### Verified — all five checks passed 2026-10-21

Our server appears as an **eighth** entry named `linear`, separate from `claude.ai Linear`.

- [x] `linear` loads as a project MCP server; `claude.ai Linear` stayed on "needs
      authentication" and was **not** approved
- [x] **No browser, no consent screen.** The bearer-key path, as intended
- [x] Tool list is **read-only in full** — every tool is `get_*`, `list_*` or `search_*`.
      No create, update or delete tool exists on the endpoint
- [x] **Team scoping took.** `list_teams` returns exactly one team, `QA`. `get_issue
      GRP-3163` errors with `invalid_request / Could not find referenced Issue`
- [x] `git grep lin_api_` returns only the literal `lin_api_...` placeholder in README,
      HANDOFF and LINEAR-SETUP. No real key is tracked

Reads confirmed working against QA-276, QA-541, QA-617, QA-305 and a 50-issue team listing.

### What the key actually reaches — narrower than planned

**One team: `QA`.** And `QA` in Linear is not the product team — it is the **onboarding and
training team**. Nearly every issue sits in a per-tester project ("Eri Quinonez - Onboarding
of New tester", "Jawunn Posey: Onboarding of New Tester", "Emily Acuña - Onboarding of New
Tester"). The product work this repo is meant to serve lives under **GRP, DRI, BUG, EIN** —
**none of which the key can see.**

Consequences, measured rather than assumed:

- **GRP-3163 cannot be scraped.** One of the two practice runs is out of reach entirely.
- **The three benefits claimed below did not materialise for QA-276** — see the correction
  in that section.

**This is the open decision for Connor:** widen the key's team scope to the product teams,
or accept that Linear access only covers QA-team tickets. The comments, PRs and releases the
Stage C case was built on live on the teams the key can't currently reach.

### Possible blockers

Admins can disable member API keys workspace-wide (Settings → Administration → API). A key
never exceeds its creator's access. One auth session is one workspace.

### What Stage C actually buys — and it isn't the paste

Pasting is ten seconds. Two things are worth having:

1. ~~**Everything in Linear that isn't the description box.**~~ **Checked 2026-10-21 —
   this did not hold for QA-276.** Each of the three claims failed against the real ticket:

   - **Comments:** QA-276 has **zero**. So do QA-541, QA-617 and QA-305. This QA team does
     not use comments. *"UI for where the button lives PENDING"* was never settled anywhere
     in Linear — it still reads PENDING on the live twin nine months later.
   - **Project resolves Release Introduced:** no. Projects here are per-tester onboarding
     projects, not releases. **Release Introduced is still unknown.**
   - **The linked PR:** `attachments` is empty and `relations` is empty on QA-276. There is
     no linked PR.

   What Linear *did* give that the paste did not: the `Android` label confirmed as the only
   platform tag, `Done` / `completedAt 2026-10-19`, and — the one genuinely valuable find —
   **QA-541**.
2. **The Structured block getting filled in.** On both practice runs it was left blank and
   drafting read the raw body — losing every decision made along the way. Both were
   backfilled 2026-10-21; the open-questions lists are now the most useful thing in each
   folder. **This one holds** — and it never depended on Linear access.

### QA-276 is a stale copy. QA-541 is the live one.

Found by listing the QA team rather than by reading QA-276 itself:

| | QA-276 | QA-541 |
|---|---|---|
| Project | Eri Quinonez - Onboarding of New tester | Jawunn Posey: Onboarding of New Tester |
| Status | Done (completed 2026-10-19) | **Backlog** |
| Build link | Build 1 | ~~Build 1~~ struck through, **Build 2** |
| Created | 2026-01-07 | 2026-07-09 |

Same title, same body, same unresolved ACs. **This settles the "re-file or new iteration?"
question in the open items: neither — it is a training exercise re-filed per onboarding
tester, and QA-541 is the current instance carrying the current build.**

`runs/QA-276/` therefore points at the superseded copy. If that run is ever executed rather
than used as practice, it should be repointed at **QA-541 and Build 2**.

Full setup: `docs/LINEAR-SETUP.md`. The skill: `.claude/skills/ticket-scrape/SKILL.md`.
Access has landed for the `QA` team. For tickets on any other team the paste fallback is
still the only route:

```bash
pbpaste | python3 tools/new_run.py GRP-3163 --ticket -
```

---

## Stage C is finished — the loop ran end to end

**QA-642, 2026-10-21.** Ticket fetched from Linear, coverage checked, decision written,
five cases drafted and proofed, published as sub-issues QA-676–QA-680, reviewed by Connor
in Linear, one case reworked from comments and renamed in place, all five approved. The
watcher exited on its own with `ALL CASES APPROVED`.

That meets Stage C's written bar: *one command takes a ticket ID and produces a reviewed
case set, with no copy-paste.*

### Stage D was answered by Stage C, not built

The rollout planned a bespoke HTML review view. It isn't needed: **Linear is the review
surface.** Cases are sub-issues; comments are the instruction; status is the verdict. The
team already works this way — QA-623 has eighteen human-written cases filed as sub-issues.
Nothing about Stage F (the evidence view) depends on the Stage D generator existing.

### What was added

- `tools/review_sync.py` — `publish`, `poll`, `watch`, `status`, `stage`
- `.claude/commands/sprint.md` and `rework.md`; `tools/sprint.sh` runs the same thing from
  a terminal
- `tools/new_run.py --linear` — fetches the ticket over GraphQL. The old rule "the fetch is
  the model's job" was about MCP, which only a model client can speak; a GraphQL call is
  deterministic and belongs in `tools/`
- `CLAUDE.md` — the operating rules, loaded by any session in this repo
- `07-questions.md` in a run folder — what the run is blocked on and who owns each answer

### Writes live in the script, not in MCP

`.mcp.json` still points at `/mcp/readonly`, and the agent session holds **no write tool**.
Every write goes through `review_sync.py` over GraphQL, creating and updating sub-issues of
one named parent. A model holding `issueCreate` can write anything anywhere; a script does
a fixed set of operations you can diff. **Don't move writes into MCP to save a step.**

One allowlist line was added: `POST https://api.linear.app/graphql`.

### Bugs found and fixed, worth not re-introducing

- **The comment filter discarded the reviewer's comments.** The key is Connor's, so
  `viewer` *is* Connor; "ignore my own comments" excluded exactly the ones that mattered.
  Filter by timestamp; mark anything the script posts with `[co-driver]`.
- **Renames created duplicates.** The update mutation never sent `title`, and issues were
  matched *by* title. Titles now update, and a rename is paired by file position with the
  old and new names printed.
- **Platform labels are workspace-level**, not team-level, so `team { labels }` returned
  nothing. Query both.
- **`--linear` skipped candidate scoring**, so a fetched run had no `00-candidates.md`.
- **The watch loop wrote and announced an empty rework file every cycle**, burying the real
  output.

### Still unproven

**The `--on-rework` hook has never fired unattended.** Polling, comment detection, rename
and republish are all proven; `/rework` running without a human watching is not. To test
it: leave a *new* comment (a state move alone is correctly ignored) on a case that is not
already final.

## Built in the last session

- `.claude/skills/ticket-scrape/` — ticket → filled-in `01-summary.md`
- `.mcp.json`, `docs/LINEAR-SETUP.md`
- `new_run.py --ticket -` (stdin), and Config + Backend added to the summary template so
  all three configuration axes get asked for, not just OS
- **Steps are numbered now**, 1..n. `validate_cases.py` treats a bulleted step as an
  **error**, and numbering that isn't 1..n in order as an error. Preconditions and Expected
  Results stay bulleted — they're a set, not a sequence. All three existing case files were
  backfilled (81 steps) and revalidate at 0 errors
- Structured blocks backfilled on `runs/QA-276/` and `runs/GRP-3163/`

## Open items

**Decisions waiting on Connor:**

- **Widen the Linear key's team scope?** It currently covers `QA` only, which is the
  onboarding team. The product teams — GRP, DRI, BUG, EIN — are unreachable, and that is
  where the comments, PRs and releases Stage C was justified on actually live. Keeping the
  scope tight is a defensible choice; it just means Linear access buys less than planned

- `~/.claude/skills/{coverage-check,case-draft}` and `~/.claude/agents/case-proofer.md` are
  duplicates of the in-repo copies and will drift. Fix is symlinks into the repo — proposed,
  not done, because it changes his home config.
- **Nothing is committed yet.** Connor commits in GitHub Desktop; never run git for him
  beyond read-only.

**Data/process cleanups:**

- Flag capitalization in Testmo: 61 cases on `Enable_` vs 100 on `enable_`
- Re-export the CSV — Steps/Preconditions/Goal date from 2026-10-13
- C330662 has a corrupted expected-result string
- Consider a Testmo custom field for **Backend** (no field exists; it's stated in metadata
  and Preconditions for now)
- The effort ledger in the rollout doc is still blank

**Unresolved on the practice tickets:**

- **QA-276** — ~~re-file or new iteration?~~ **Answered 2026-10-21: an onboarding training
  exercise, re-filed per tester. QA-541 is the live instance (Build 2).** Still open: **"IA"
  is undefined** and case 2 isn't executable until someone says what surface support
  actually uses. Linear did not answer it — there are no comments on the ticket.
  **Release Introduced is also still unknown**; the project field does not supply it
- **GRP-3163** — how to provision an account on an old-format token; whether QA verifies
  token internals; C662431's OS restriction. **Note: the Linear key cannot reach the GRP
  team, so this one stays paste-only until the key's scope is widened**
- **PIN-V2-GAP** — dropped deliberately or missed?

## The rule that governs all of it

**The floor is always a scoped pass on the area that changed** — feature, dependency
upgrade, or a refactor meant to behave identically. "No new functionality" means no new
*cases*. It never means skip the area.
