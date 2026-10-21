# Dispatch / Co-Driver

A QA loop for the Eleos mobile app: a Linear ticket goes in, the right test coverage comes
out, gets run, and gets reported back to Testmo.

The point is not automation for its own sake. It is that **nothing ships without an
inspection of the area that changed** — and that the mechanical parts of producing that
inspection (reading the ticket, finding what already covers it, drafting what doesn't exist,
proofing it) stop costing a person their afternoon.

## Layout

```
tools/      the four scripts — the facts
.claude/    skills and agents — the judgment
docs/       the thesis, the rollout plan, the prompts, Linear setup, the handoff
runs/       one folder per ticket (git-ignored)
.mcp.json   Linear, read-only endpoint + read-scoped key
```

`tools/` is deterministic and auditable: fetch, normalize, count. `.claude/` is where the
decisions live. The split is deliberate — a number should never depend on which model
answered.

## Setup

```bash
cp .env.example .env          # then fill in your Testmo token
python3 tools/refresh.py      # pulls the live repository, ~40s

export LINEAR_API_KEY=lin_api_...     # in ~/.zshrc, not in .env — see docs/LINEAR-SETUP.md
```

Two secrets, two mechanisms, and the difference matters: `.env` is parsed by `refresh.py`
in Python, so the shell never sees it. `.mcp.json` expands `${LINEAR_API_KEY}` from the
shell environment, so that one has to be exported. `.mcp.json` itself holds no secret and
is committed.

`refresh.py` issues **GET only**, and the proxy allowlist carries no write method.
Don't add one.

## The tools

| Script | Job |
|---|---|
| `tools/refresh.py` | Pull the live Testmo repository and build the local cache |
| `tools/coverage.py` | Every query — `areas`, `area`, `search`, `case`, `suggest`, `health` |
| `tools/new_run.py` | Start a run folder for a ticket and score candidate areas |
| `tools/validate_cases.py` | Mechanical checks on drafted cases before a human reads them |

```bash
python3 tools/coverage.py areas pin
python3 tools/coverage.py area "Pin" --full
python3 tools/coverage.py search "rescan request"
```

The commands are shortcuts, not the ceiling. The cache is normalized JSON — for a question
that doesn't fit a command, write a few lines of Python against it.

## The skills

These load automatically when Claude Code runs with this repo as the working directory.
You ask a question; the skill fires. There are no commands to memorize.

| | What it answers |
|---|---|
| `ticket-scrape` | Ticket ID → a filled-in run summary, including what the body doesn't say |
| `coverage-check` | "What covers this area, is it still valid, what's missing?" |
| `case-draft` | Ticket → decision → cases in house format |
| `case-proofer` *(agent)* | Independent review, fresh context, no knowledge of how the cases were produced |

## Where this is

**Picking this up cold? Read `docs/HANDOFF.md`.**

Built and working: the coverage answer, ticket-to-cases, and the ticket scrape. Testmo
access is live and read-only; Linear access needs one allowlist line and a read-scoped key
(`docs/LINEAR-SETUP.md`), and until then the scrape runs off pasted ticket text, which
costs only the comments and the links. The device leg and reporting back out
are still ahead — see
`docs/Claude-Sprint-Workflow-Rollout.md` for the staging, and
`docs/Claude-Sprint-Workflow-Thesis.md` for what's feasible and what it needs.

## The rule that governs all of it

**The floor is always a scoped pass on the area that changed** — whether the ticket adds a
feature, upgrades a dependency, or refactors something meant to behave identically. "No new
functionality" means no new *cases*. It never means skip the area.




● Allowlist line is right. But both other pieces are still missing — I can see it from inside the session:

  - Running from /home/vm, not the repo → .mcp.json isn't read, so linear never appears
  - LINEAR_API_KEY isn't set in this session's environment

  That's why the list still shows only the seven claude.ai connectors.
  
  Exit, then run these three lines in the same terminal, in this order:

  export LINEAR_API_KEY=lin_api_...
  cd /home/vm/shared/Dispatch-Co-Driver
  claude

  The cd has to happen before claude, and the export has to be in that same shell. Launching from anywhere else gets you exactly what you're seeing now.

  To make it stick across reboots (this is the VM, so bash):

  echo 'export LINEAR_API_KEY=lin_api_...' >> ~/.bashrc

  Once you're in, /mcp should list linear as an eighth server. If it's there, we're wired up — connected if the allowlist line is live, 418 on /mcp/readonly if it hasn't been picked up yet. Either
  way that tells us it's our server and not the connector.

✻ Baked for 14s · done 2:13 AM

❯ sorry I have been using claude in a VM and doing the actual work inside of the terminal but not in the vm in taht makes sense I think I just have tgo find the loop here but should be doable     

● That makes sense, and it's the exact distinction this whole project is built around — so worth pinning down once.
  
  Claude Code runs in the VM. So everything about the MCP server is a VM thing:

  - .mcp.json — the VM's checkout, /home/vm/shared/Dispatch-Co-Driver
  - LINEAR_API_KEY — exported in the VM's shell                                                                                                                          
  - the proxy — it's the VM's traffic that gets allowlisted

  The one piece that lives on the Mac is allowlist.txt, next to filter.py on the host. That's probably where the confusion came from: two different machines for two steps that feel like one task.

  Whatever window you type claude into is the VM shell. Easiest way to stop fighting the ordering:

  echo 'export LINEAR_API_KEY=lin_api_...' >> ~/.bashrc

  Run that once in the VM and the key is set for every shell from then on. After that you only ever need:

  cd /home/vm/shared/Dispatch-Co-Driver
  claude

  Since the share is the same files on both sides, .mcp.json shows up on the Mac too — but it only does anything where Claude Code actually runs, which is the VM.

  Your Mac terminal isn't wasted, by the way. That's Stage E — the device leg runs there because that's where the phones are, in its own Claude session. Same repo through the share, different
  machine, different job. Nothing to set up for it yet.

❯ /usage 
  ⎿  Settings dialog dismissed

✻ Crunched for 24s · done 2:17 AM
