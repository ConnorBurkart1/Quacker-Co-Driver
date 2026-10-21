# Handoff — state as of 2026-10-21

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
| **C — read-only access** | **Half.** Testmo live; Linear wired but not yet connected — see below |
| **D — review view** | Not started. Optional by design |
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

## Linear — wired, not yet connected

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

### What is still outstanding (unverified as of 2026-10-21)

1. `POST https://mcp.linear.app/mcp/readonly` in `allowlist.txt` **on the host**, next to
   `filter.py`.
2. `LINEAR_API_KEY` exported in **the VM's** shell — `~/.bashrc`, not `.env`. `.env` is
   parsed by `refresh.py` in Python; the shell never sees it, and `${LINEAR_API_KEY}` is
   expanded by the shell environment at server load.
3. Claude Code **launched from the repo root**. Project MCP servers are read from
   `.mcp.json` in the working directory.

```bash
echo 'export LINEAR_API_KEY=lin_api_...' >> ~/.bashrc    # once, in the VM
cd /home/vm/shared/Dispatch-Co-Driver
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

### Verify before trusting it

Our server appears as an **eighth** entry named `linear`, separate from `claude.ai Linear`.

- [ ] `/mcp` lists `linear`
- [ ] **No browser, no consent screen.** That's how you know it's the bearer-key path
- [ ] Tool list contains **no create/update/delete tools**. If a write tool appears, stop —
      the endpoint isn't doing what we think
- [ ] Reading an issue in a team the key doesn't cover **errors**. If it succeeds, the team
      scoping didn't take
- [ ] `git grep lin_api_` → nothing

The second, third and fourth turn "Linear says it's read-only and team-scoped" into
something observed rather than assumed.

### Possible blockers

Admins can disable member API keys workspace-wide (Settings → Administration → API). A key
never exceeds its creator's access. One auth session is one workspace.

### What Stage C actually buys — and it isn't the paste

Pasting is ten seconds. Two things are worth having:

1. **Everything in Linear that isn't the description box.** Comments especially: QA-276's
   body says *"UI for where the button lives PENDING"* and on a ticket that old somebody
   almost certainly settled it in a comment. Labels carry platform tags, the project
   resolves **Release Introduced**, the linked PR is the only honest signal of what code
   actually changed.
2. **The Structured block getting filled in.** On both practice runs it was left blank and
   drafting read the raw body — losing every decision made along the way. Both were
   backfilled 2026-10-21; the open-questions lists are now the most useful thing in each
   folder.

Full setup: `docs/LINEAR-SETUP.md`. The skill: `.claude/skills/ticket-scrape/SKILL.md`.
Until access lands the fallback costs only the comments and the links:

```bash
pbpaste | python3 tools/new_run.py QA-276 --ticket -
```

---

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

- **QA-276** — is it a re-file of shipped work or a new iteration? "IA" is undefined and
  case 2 isn't executable until someone says what surface support actually uses
- **GRP-3163** — how to provision an account on an old-format token; whether QA verifies
  token internals; C662431's OS restriction
- **PIN-V2-GAP** — dropped deliberately or missed?

## The rule that governs all of it

**The floor is always a scoped pass on the area that changed** — feature, dependency
upgrade, or a refactor meant to behave identically. "No new functionality" means no new
*cases*. It never means skip the area.
