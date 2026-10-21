# Claude Sprint Work — Rollout Plan

**How we build it, in stages — designed around the smallest possible amount of effort to use.**

**Author:** Connor Burkart · **Date:** 2026-10-20 · **Status:** Companion to the Workflow Thesis

---

## 0. How to read this alongside the thesis

The thesis answers **"is this possible, and what does it need?"**

This answers **"what does it feel like to use, and in what order do we build it?"**

They're deliberately separate, because the honest answer to the first question is mostly yes, while
the honest answer to the second is *it depends entirely on how much work it is to drive*. A loop
that's technically complete but takes fifteen decisions to run is a loop nobody runs twice.

So the governing constraint for everything below:

> **Every stage we build has to make a sprint ticket cheaper to test than it was the week before —
> measured in Connor's attention, not in features shipped.**

If a phase doesn't pass that test, it isn't ready, no matter how much of it works.

---

## 1. The experience we're aiming at

Here's the whole thing, as it should look from the outside once it's finished. This is the target,
not a description of anything that exists today.

```
$ /sprint LIN-1847

  Reading LIN-1847 … "Driver can dismiss the pre-trip inspection reminder"

  ── Summary ───────────────────────────────────────────────────
  Area:        Inspections / Home screen
  Type:        New functionality
  Platforms:   Android + iOS
  Flags:       inspection_reminder_v2  (ON in QA)
  Risk:        Dismiss state may persist across logout; reminder
               interacts with the HOS clock banner.
  Open Q:      Does dismissal survive app restart, or only the session?

  ? Summary look right?  [Yes / Edit / Open ticket]   ›  Yes

  Checking existing coverage … 14 cases in Inspections, 3 automated

  ── What we already have ──────────────────────────────────────
  C1120  Pre-trip inspection required before drive     automated
  C1121  Inspection reminder appears at shift start    manual
  C2890  Reminder persists after background/foreground manual
  … 11 more

  Gap:  nothing covers dismissal, and C2890's assumption that the
        reminder always returns is now conditional.

  Recommendation:  4 new cases, 1 existing case needs updating,
                   plus a scoped regression on Inspections (6 tests).

  ? Proceed?  [Yes / Change scope / Stop here]   ›  Yes

  Drafting cases … proofing against a fresh instance … 2 disagreements

  ── Review ────────────────────────────────────────────────────
  Open:  runs/LIN-1847/review.html
         (4 new, 1 edit, 2 flagged for you)

  ? Approved?  [Yes / Open review / Stop here]   ›  Yes

  Writing to Testmo … done.  Run "LIN-1847 — manual" created.

  Device work runs on the Mac.  In that session:  /sprint LIN-1847 --device
```

**Four decisions. One command. Everything else is a file you can open if you want to and ignore if
you don't.**

That's the bar. Every design choice below is in service of it.

---

## 2. The five design rules

These are the rules that make the difference between "it works" and "it's effortless." Worth
agreeing on them before any of it gets built, because they're expensive to retrofit.

### Rule 1 — One command, one ticket

Not eight commands for eight stages. `/sprint LIN-1847` is the whole interface, and running it again
on the same ticket **resumes where it stopped**. No flags to remember, no order to get right.

The stages still exist as separate skills — they have to, for testing and for reuse — but they are
not the user interface. The orchestrator is. (The thesis calls the orchestrator "last, not first,"
and that's still true for *building* it. But it should be designed first, because it determines what
shape the stages need to have.)

### Rule 2 — The run folder is the state, and it's human-readable

Everything the loop knows lives in one folder per ticket, in plain Markdown:

```
runs/LIN-1847/
  STATUS.md            ← the one file a human opens
  01-summary.md
  02-cases.md
  03-coverage.md
  04-decision.md
  05-proof.md
  06-execution/
      run.md
      evidence/        ← screenshots, named by case and step
  07-regression.md
  08-report.md
  review.html          ← generated; see §4
```

Three things fall out of this for free, and they're the reason it's a rule rather than a detail:

- **Resumability.** The folder *is* the state, so a session that dies loses nothing and a session
  started tomorrow picks up cleanly.
- **Correctability.** Connor can fix a wrong summary by editing `01-summary.md` in his editor, not by
  arguing with a chat window. Everything downstream reads the corrected file.
- **Auditability.** When somebody asks "why did it test that?", the answer is a file, not a
  transcript nobody kept.

`STATUS.md` is the front door — stage checklist, what's waiting on a human, what the next command is.
If a person opens exactly one file, it's that one.

### Rule 3 — Default to acting, ask only where it's expensive to be wrong

Four gates, from the thesis — summary, cases, device run, outward write. Not five, not nine. Every
other decision the loop makes itself and records in the run folder, where it can be reviewed after
the fact rather than approved in advance.

The anti-pattern to avoid by name: a loop that asks permission at every stage boundary feels
*safer* and is actually *worse*, because approval fatigue turns every gate into a reflexive yes —
including the two that matter.

### Rule 4 — Review in a surface built for reviewing

Reading 20 generated test cases in a Markdown file, in a terminal, is the single worst moment in the
flow as designed. It's also the moment that most determines output quality, because it's gate 2.

So that one surface gets real attention. See §4 — it's the only place a UI clearly earns its keep.

### Rule 5 — Any UI writes a file; Claude reads the file

A review page that holds decisions in the browser is a dead end — Claude can't see them. So the
contract is fixed from the start: **the UI's only job is to produce `review-decisions.json` in the
run folder.** Claude reads that file and acts on it.

This keeps the UI optional at every stage. If the page breaks, is inconvenient, or is on the wrong
machine, editing the Markdown by hand does exactly the same thing. Nothing is ever *only* reachable
through the UI.

**And it means the UI is a question we can defer.** Stage D is the one stage in this plan that can
be dropped entirely without touching anything else — the loop works end to end with Markdown review
and nothing else. The argument for building it is narrow and specific: reviewing a large case set in
a terminal is unpleasant enough that it degrades gate 2, which is the gate that most determines
output quality. **If that turns out not to be true in practice — if reviewing 20 cases in Markdown
is fine — then Stage D shouldn't be built.** Worth deciding from experience at Stage B rather than
from a guess now.

---

## 3. Where the interface actually lives

Worth being concrete about this, because "maybe a UI" can mean five different things with very
different costs.

| Surface | What it's for | Build cost | Verdict |
|---|---|---|---|
| **Slash command in Claude Code** | Driving the loop | ~none — it's a file | **The primary interface.** Already exists as a mechanism |
| **Built-in question prompts** | The four gates | none | **Already a UI.** Don't build a second one |
| **Markdown in the run folder** | State, correction, audit | none | **The substrate.** Everything else is a view onto it |
| **A generated review page** | Gate 2 — approving cases | small, one file per run | **Optional** (Stage D) — drop it if Markdown review turns out to be fine |
| **A generated evidence view** | Showing what a device run actually did | small — *same generator*, second view | **Build it** (Stage F). The one surface worth showing people |
| **A cross-run dashboard** | Showing the team what's happening over time | medium | **Last.** A pitch asset, not a tool |
| **A full app / control panel** | Driving the loop from a GUI | large | **No.** It would be a worse terminal |

The useful distinction: **a UI is good at showing many things at once and collecting structured
decisions. It's bad at being a command line.** Driving a sequential process is what terminals are
for, and we already have one with gates built in.

So: the loop is driven from the terminal, reviewed in a browser page, and stored in Markdown.

### One constraint that shapes this

The review page should be **a plain HTML file in the run folder, opened from disk** — not a hosted
page. Three reasons, all practical: the sandboxed VM can't reach hosted pages anyway; test case
content and device screenshots are internal and shouldn't leave the building just to be looked at;
and a file in the run folder is still there in six months when someone asks what was approved.

It's a single self-contained file with the cases inlined. No server, no build step, no dependencies.
Double-click it.

---

## 4. The two views, and one generator

There are two pages worth considering, and they are **the same program**: one script that walks a run
folder and emits self-contained HTML. Two views over the same files.

- **The review view** (Stage D, optional) — gate 2. Internal plumbing. Makes your Tuesday better and
  makes no impression on anyone else.
- **The evidence view** (Stage F) — what a device run actually did. **This is the one worth showing
  people**, and it's the reason the generator is worth writing at all.

Because they share a generator, building either one makes the other nearly free. That's what makes
the review view safe to build without committing to it, and the evidence view cheap to add once
there's something to show.

### 4a. The review view — gate 2

The shape:

```
┌─────────────────────────────────────────────────────────────────┐
│  LIN-1847 — Dismiss pre-trip inspection reminder                │
│  4 new cases · 1 edit · 2 flagged by proofing      [Approve all] │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ⚑  NEW — Dismiss reminder, verify it stays dismissed            │
│     Folder: Inspections / Reminders      Restricted to: Android  │
│                                                                  │
│     Preconditions   Driver logged in, shift started, reminder    │
│                     visible on Home                              │
│     1. Tap "Dismiss" on the inspection reminder card             │
│        → Card disappears, Home list reflows                      │
│     2. Background the app for 30s, return                        │
│        → Reminder does not reappear                              │
│     3. Log out and back in                                       │
│        → ??? proofing disagreed — see note                       │
│                                                                  │
│     ⚑ Proofing note: the ticket doesn't say whether dismissal    │
│       survives logout. Draft asserts it does. That's an          │
│       assumption, not a requirement.                             │
│                                                                  │
│     [ Approve ]  [ Edit ]  [ Reject ]  [ Ask the ticket author ] │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│  ✓  NEW — Reminder returns on next shift after dismissal         │
│     … collapsed, already approved …                   [ Reopen ] │
└─────────────────────────────────────────────────────────────────┘
```

The design decisions that matter here:

- **Flagged cases sort to the top.** Where the proofer disagreed with the draft is where Connor's
  attention is worth the most. Everything it agreed on can be skimmed or bulk-approved.
- **"Approve all" exists and is fine.** If the top-of-list flags are clean, bulk approval is a
  reasonable, informed action — not a shortcut. Making it hard would just train the habit of
  clicking through individually without reading.
- **Edit is inline and writes back to `02-cases.md`.** Not a comment for Claude to interpret — the
  actual text that gets written to Testmo. Fewer round trips, no translation loss.
- **"Ask the ticket author" produces copy-paste text**, not a Linear write. Keeps the ask small and
  matches how GitHub and Linear are already driven by hand.
Everything on this page is a view of files that already exist. The page is a convenience, never a
dependency.

### 4b. The evidence view — what the run actually did

Same generator, different view, and a different purpose: this one is for people who weren't
watching.

```
┌─────────────────────────────────────────────────────────────────┐
│  LIN-1847 — manual run        Pixel 7 · Android 14 · build 4821 │
│  5 cases · 4 passed · 1 failed · 1 exploratory session          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ✗  C-NEW-2  Dismiss reminder, verify it stays dismissed         │
│     ──────────────────────────────────────────────────────────  │
│      1 ✓  Tap "Dismiss" on the reminder card     ┌──────────┐   │
│           Card disappeared, Home reflowed        │ [screen] │   │
│                                                  └──────────┘   │
│      2 ✓  Background 30s, return                 ┌──────────┐   │
│           Reminder did not reappear              │ [screen] │   │
│                                                  └──────────┘   │
│      3 ✗  Log out and back in                    ┌──────────┐   │
│           Reminder RETURNED. Expected: stays     │ [screen] │   │
│           dismissed.                             └──────────┘   │
│                                                                  │
│           ⚑ This was the assumption proofing flagged at gate 2. │
│             Needs a product answer before it's filed as a bug.  │
│                                                                  │
│  ⊙  Exploratory — Inspections, 18 min, 41 steps                  │
│     Charter: what nearby behavior could dismissal disturb?       │
│     2 observations · 1 worth filing            [ Expand ]        │
└─────────────────────────────────────────────────────────────────┘
```

Why this is the one worth building:

- **It's the proof.** A manual run with no evidence is a claim. With per-step screenshots it's a
  record somebody else can check without re-running anything.
- **It carries the flagged assumptions forward.** The thing proofing was unsure about at gate 2
  shows up again here, at the exact step where it got answered by the device. That closes a loop
  nothing else closes.
- **It makes exploratory work legible.** An exploratory session is otherwise the hardest thing to
  report — a path nobody will walk again. The view turns it into something with a charter, a
  duration, and findings attached to screenshots.
- **It's what feeds stage 8.** The same evidence attaches to the Testmo result. Generating the view
  and generating the report are mostly the same work.

**The honest caveat on sequencing:** a polished page over unproven output is worse than no page,
because it invites scrutiny of the thing underneath. This gets built after the device leg works —
when it's showing something nobody has seen before, rather than a list of test cases in a nicer
font.

---

## 5. The stages — what we build, and what it buys

Each stage below is scoped so it's **independently useful**. If we stop after any one of them, the
work done so far still pays for itself. That's deliberate: it's what makes this safe to start without
committing to finishing.

The effort column is the point. Fill in real numbers as we go — they're the argument.

---

### Stage A — The coverage answer *(no access needed)*

**Build:** the context checker skill, reading the Testmo export already on disk.

**What Connor does:** asks a question in plain language — *"what covers the inspection reminder?"* —
and gets back the cases, what each actually verifies, and what's missing.

**What it buys:** the single most common manual lookup in the job, answered in seconds instead of
clicking through Testmo folders. **Useful on its own, immediately, with zero process change.** Nobody
has to adopt a workflow to benefit from it.

**Why it's first:** no network, no dependencies, no permissions conversation, no risk. It's also the
cheapest possible proof that this is worth continuing — if the coverage answers aren't good, we find
out in week one for almost nothing.

**Done when:** it answers three real area questions better than opening Testmo would have.

---

### Stage B — Ticket in, cases out *(no access needed)*

**Build:** the case-generation skill, the proofing agent, and the run folder structure. Ticket text
is pasted into `01-summary.md` by hand for now.

**What Connor does:** pastes the ticket, runs one command, reads the draft cases in Markdown.

**Validation material already exists.** There are practice tickets we can run this against — real
ones, with known-good outcomes, where the right answer is already understood. That's a much better
test bed than waiting for a live sprint ticket: we can run the same ticket repeatedly while tuning
the skill, compare against what was actually tested, and find out the real quality level without a
sprint riding on it.

**What it buys:** the drafting time on new cases, which is the biggest single block of manual work in
a sprint. Reviewing is much faster than writing, even when the review is thorough.

**Why here:** it depends on Stage A (cases are drafted against known coverage, not in a vacuum) and
on nothing else. It's also where we learn the real quality level, early, while the output is still
cheap to throw away because nothing's being written to Testmo yet.

**Done when:** on a real ticket, the generated cases are closer to final than a blank page is —
and we can say by how much.

---

### Stage C — Access, read-only *(one small ask)*

**Half done.** Splitting it by system turned out to matter, because the two halves needed completely
different things.

**Testmo — done.** Not through the MCP connector, which we were never invited to, but through the
REST API with a token in `.env`. That turned out to be the better answer anyway: REST puts the verb
in the HTTP method, so a `GET`-only allowlist line enforces read-only *at the network boundary*. MCP
is JSON-RPC over a single endpoint with the verb in the request body, which the proxy cannot see
into. There is no read-only token tier in Testmo, so that one allowlist line is the entire
enforcement — which is why `refresh.py` issues GET only and the allowlist carries no write method.

**Linear — outstanding, and it's one line.** Two independent locks, both on Linear's side: the
read-only endpoint, which only ever exposes read tools, and a personal API key restricted to `Read`
and to selected teams. Not OAuth — dynamic client registration wants an interactive browser the VM
doesn't have, and several more allowlist entries. A bearer key needs one:

```
POST https://mcp.linear.app/mcp/readonly
```

POST is how MCP talks, not a write — every JSON-RPC message goes as a POST body to the one endpoint.
Which is the whole reason the locks have to be Linear's rather than the proxy's. Setup, and the
verification that turns "Linear says it's read-only" into something observed, in
`docs/LINEAR-SETUP.md`.

**Build:** the `ticket-scrape` skill — written, and useful before the access lands.

**What Connor does:** names a ticket. Stops pasting, once the rule is in.

**What it buys — and it is not the paste.** Pasting is ten seconds. Two things are worth having:

1. **Everything in Linear that isn't in the description box.** Comments especially: QA-276's body
   says *"UI for where the button lives PENDING"*, and in a ticket that old it is near-certain that
   somebody settled it in a comment. Drafting off the body alone writes cases against a screen that
   may not exist. Labels carry platform tags, the project resolves **Release Introduced**, and the
   linked PR is the only honest signal of what code actually changed.
2. **The Structured block gets filled in.** On both practice runs it was left blank and drafting
   worked straight off the raw ticket. That works — and it throws away every decision made along the
   way. Nothing recorded which areas were rejected, whether a flag was checked, or what nobody knew.
   Both practice summaries have now been backfilled, and the open-questions list each one produced is
   the most useful thing in the folder: QA-276's says *case 2 is not executable until someone defines
   "IA"*, which is a blocker worth knowing before a tester picks it up, not after.

**Why here:** it's the first thing that needs permission from anyone else, and by this point there's
something working to point at when asking. Asking for read-only access to show a working thing is a
much easier conversation than asking for access to build an idea.

**Done when:** one command takes a ticket ID and produces a reviewed case set, with no copy-paste.

---

### Stage D — The review view *(optional, no access needed)*

**Build:** the run-folder HTML generator, its review view, and the `review-decisions.json`
contract.

**Optional by design.** Everything downstream works without it. Build it only if Stage B shows that
reviewing case sets in Markdown is slow enough to degrade gate 2. If it does get built, the
generator is reused by Stage F, so none of the work is stranded.

**What Connor does:** opens one file, skims what proofing agreed on, reads the two things it didn't,
approves.

**What it buys:** gate 2 stops being the slow part. This is also the stage that makes the loop
*shareable* — somebody else on the team can review a case set without understanding any of the
machinery underneath.

**Why here, and not earlier:** there has to be something worth reviewing before the review surface
matters. Building it before Stage B would be designing a UI for output we hadn't seen yet.

**Done when:** reviewing a full case set takes less time than reading them in a terminal did, and
the decisions land correctly in the run folder.

---

### Stage E — The device leg *(runs on the Mac)*

**Build:** the execution and exploratory skills, on the Mac session, scoped to one area of the app
first.

**What Connor does:** in a Mac session, `/sprint LIN-1847 --device`. Watches the first few. Stops
watching once it's boring.

**What it buys:** the execution time, which is the largest block of all — and exploratory coverage of
nearby areas that wouldn't have been checked by hand at all.

**Why here:** it's the highest-value stage and the one with the most real-world variables, so it
wants the earlier stages solid underneath it. It also needs a human present at first, which makes it
the stage most worth sequencing after the ones that don't.

**Two things it needs that aren't built:** the Android reference repo in `shared/`, and a measured
cost number for one scoped crawl before anything gets promised about whole-app sweeps.

**Done when:** a scoped run on one area produces evidence a human would accept as a real test run —
and we know what it cost.

---

### Stage F — The evidence view *(no access needed)*

**Build:** the second view of the Stage D generator — per-case, per-step, screenshot, pass/fail, plus
the exploratory session summary. Shape is in §4b.

**What Connor does:** sends a link to a file instead of describing what happened.

**What it buys:** this is the stage that makes the work *visible*, and it's the first thing in this
plan that other people will look at. A manual run with no evidence is a claim; a manual run with
per-step screenshots is a record anyone can check. It also makes exploratory sessions reportable at
all, which is otherwise their weakest property.

**Why here, specifically:** it needs the device leg working, because its entire value is showing
something nobody at Eleos can currently produce. Built before Stage E it has nothing to display.
Built after, it's the artifact that makes the case for the whole project without anyone needing to
understand the machinery.

**Why it's cheap:** same generator as Stage D, and most of the same work feeds Stage G's Testmo
report. Three jobs, one script.

**Done when:** somebody who wasn't in the room can open it and say what was tested, what happened,
and what's in question — with no narration from Connor.

---

### Stage G — Reporting out *(write access, one system at a time)*

**Build:** the Testmo write path for manual results and exploratory sessions, then the Linear
sub-issue.

**What Connor does:** approves once at gate 4. Results land in Testmo as manual results, exploratory
work lands as a session, and the ticket gets its sub-issue.

**What it buys:** the write-up time, and — more durably — it closes the loop so the work is visible
to the team without Connor relaying it.

**Why last among the functional stages:** it's the only one with outward, visible side effects, and
it's much easier to grant after the gates have been exercised on real tickets.

**Done when:** a full ticket goes from Linear to a Testmo run and back to a Linear sub-issue, and
somebody who wasn't involved can follow what happened from the Testmo record alone.

---

### Stage H — The things that make it feel finished

Small, not urgent, and disproportionately responsible for whether people keep using it:

- **`STATUS.md` kept genuinely current**, so an interrupted run explains itself on reopening.
- **Good failure behavior.** When a stage fails, the run folder says what failed, what's safe to
  retry, and what needs a human — not a stack trace. Failure is going to be routine; it should be
  routine to recover from.
- **A sensible default scope.** The project and milestone encoded once, not asked every time.
- **`/sprint --last`** to reopen whatever was in flight, because the real usage pattern is picking
  something back up after an interruption.
- **The cross-run dashboard.** A third view from the same generator, this time over all of
  `runs/` — what ran, what's waiting, what found something. For the weekly update, not for
  daily use. Lower priority than the evidence view (Stage F), because a dashboard summarizes work
  while the evidence view *is* the work.

---

## 6. The effort ledger

The argument, in one table. Columns 2 and 3 get filled in from real tickets as we go — the point is
to track them honestly, including when a stage doesn't move the number.

| After | Hands-on touches per ticket | Time | What's still manual |
|---|---|---|---|
| Today | — | — | Everything |
| Stage A | — | — | Everything except the coverage lookup |
| Stage B | — | — | Paste ticket, review cases, execute, report |
| Stage C | — | — | Review cases, execute, report |
| Stage D *(optional)* | — | — | Execute, report |
| Stage E | — | — | Report, plus supervising device runs |
| Stage F | — | — | Report (but now with evidence attached) |
| Stage G | — | — | Four approvals |

**"Touches"** means: how many separate times does Connor have to stop what he's doing and engage
with this. It's the better metric, because context-switching cost is what actually makes a workflow
feel heavy — more so than minutes.

The target at the bottom row is **four touches**: the four gates. If it ends up at seven, something
in the design went wrong and this table is how we'll notice.

---

## 7. What would make this feel bad to use

The thesis has a section on what would make the project fail. This is the smaller, more likely
version: things that would make it *work* and still not get used.

1. **Too many questions.** Covered by Rule 3, and it's the easiest rule to erode one well-intentioned
   confirmation at a time. Any new gate has to displace an existing one.
2. **Review that's slower than writing.** If gate 2 takes longer than drafting by hand did, Stage B
   has negative value. This is the number to watch most closely, and the reason Stage D exists.
3. **State that lives in a conversation.** If resuming means re-explaining, nobody resumes. Rule 2
   prevents it — as long as every stage actually writes its file rather than keeping things in
   context.
4. **Silent failure.** A loop that reports success on a device run that didn't really happen is worse
   than one that crashes, because it costs trust that's slow to rebuild. Evidence capture isn't a
   nice-to-have; it's what makes the output checkable.
5. **Only Connor can run it.** If it lives in one laptop's config instead of the repo, it's a
   personal tool and it dies on vacation. Committing the skills to the repo is what makes it a team
   capability — which is also the honest answer to "why should the company invest in this."

---

## 8. What to decide before starting

Short list, and none of them block Stage A:

1. ~~**Run folder location.**~~ **Decided:** `runs/` inside this repo, visible from both
   machines through the share. The tools, the skills and the run state travel together, so a clone
   is the whole workflow.
2. ~~**Do runs get committed?**~~ **Decided: no.** `runs/` is git-ignored. A run folder is one
   person's working state on one ticket — committing it would mean merge conflicts on scratch
   files, and evidence screenshots would bloat the repo. If a particular run is worth keeping as
   history, the record that matters is the Testmo run and the Linear sub-issue, not the folder.
   Revisit only if we want a searchable archive of past decisions.
3. **Who else reviews?** If the answer is anyone besides Connor, Stage D gets more important and its
   design should account for a reviewer who doesn't know the machinery.
4. **Which Testmo project and milestone** the skills encode as their default scope.
5. **Whether `/sprint` is the right name.** Trivial, but it's the thing that gets typed every day.

---

## 9. The short version

- **The terminal drives it. Markdown holds it. One generator turns a run folder into HTML.** Two
  views: a review page (optional) and an evidence page (the one worth showing people). No app, no
  server, no dashboard nobody opens.
- **Build in the order that pays off earliest:** the coverage answer needs no permission from anyone
  and is useful on day one. Access gets asked for when there's something working to point at.
- **Four gates, and they're load-bearing.** Everything else happens without asking and gets recorded
  where it can be checked afterward.
- **The measure of success is touches per ticket, not features built.** If a stage doesn't move that
  number, it wasn't ready.
- **The thing that stands out isn't the interface.** It's a real find from an exploratory run, a
  measured before-and-after, and a workflow someone else can run. The evidence view matters because
  it makes those three legible — not on its own.
