# Claude Sprint Work — A Workflow Thesis

**Author:** Connor Burkart · **Date:** 2026-10-20 · **Status:** Scoping draft for discussion

---

## 1. The premise

Right now, a QA sprint ticket becomes tested software through one person's head and hands. Connor
reads the Linear ticket, works out what it means for testing, writes manual cases in Testmo, figures
out what existing coverage already touches it, runs the cases on a phone, pokes around the areas the
change might have disturbed, and writes the results back up.

Most of that is judgment. Some of it is mechanical.

This document proposes moving the mechanical parts — summarizing, drafting, cross-referencing,
executing, reporting — to Claude, and keeping the judgment as a small number of explicit checkpoints
where a human looks at the work before it goes anywhere.

**This is a QA workflow, not an automation workflow.** That distinction matters throughout. The
question at each stage is "what does this change mean for the quality of the app, and how do we find
out" — not "what Appium test should we write." The automated suite appears here twice, as an input
(what's already covered without a human) and as a destination (a scoped regression run). It is not
the organizing principle, and the loop produces no net-new automated tests.

The claim this document makes:

> **The majority of this loop is buildable with what already exists. One access question carries the
> ticket end. The genuinely unsolved parts are iOS and the orchestration layer.**

---

## 2. Operating assumptions

| # | Assumption | Status |
|---|---|---|
| A1 | Claude has an `adb` binary and a phone plugged into the Mac | **Given** |
| A2 | Linear is QA's ticket system; GitHub holds code and design work | **Given** |
| A3 | Claude executing written test cases and doing exploratory testing is proven, not speculative | **Given** — observed |
| A4 | Testmo stays the system of record for cases and results | **Given** |
| A5 | The **code** repo is moving to `eleostech/quackium-tests` | In flight |
| A6 | The **official test case repository** is the Testmo export at `shared/Claude-Context/CLAUDE_LOOK_HERE_FOR_OFFICAL_TEST_CASES.csv` | **Given** |
| A7 | Both Linear and Testmo are reachable as hosted OAuth MCP servers | **Given** — see §6 |
| A8 | A human reviews anything that leaves the machine | **Proposed** — see §5 |

**A5 and A6 are two different repositories and the distinction matters.** The *code* repo holds the
automated suite. The *test case* repo is Testmo — and that's the one this workflow is mostly about.

---

## 3. Where Claude runs

The sharpest finding from scoping: **this is not one Claude in one place.** Capability differs
sharply by machine, and nearly every "can we do this?" turns out to be "on which machine?"

**The VM** — the sandboxed Linux box where Claude works today. It has the live repo through a file
share (the *same* checkout as the Mac's), and its network is restricted to a host-side allowlist. It
has no device access of any kind: no USB passthrough, no `adb`, and no route to an adb server. Only
the file share and allowlisted HTTP cross its boundary.

That is deliberate, not a defect. The VM exists so an agent with code execution and autonomy doesn't
also get unrestricted network reach.

**The Mac** — phones and iPhones on USB, full network, the same live checkout. Per A1, this is where
Claude gets a device. It's also the only place that can reach the test-data API, which the VM's
allowlist blocks.

**The Mac Mini hub** — ~20 devices, a CI runner, no Claude, and critically **not available on
demand**. A destination for runs, not a troubleshooting loop.

### The resulting split

| Stages | Host |
|---|---|
| 1–5 — ticket, cases, coverage, proofing | VM |
| 6–7 — device execution, regression runs | Mac |
| 8 — reporting | VM |

The two sessions already share state through the repo and the file share. That's how work moves
between those machines today, by hand; nothing new is needed to make it work between two Claude
sessions.

---

## 4. The loop, stage by stage

Ratings: **Green** — buildable with what exists · **Amber** — needs one specific unlock ·
**Red** — needs design work before it can be estimated.

| # | Stage | Host | Rating |
|---|---|---|---|
| 1 | Read the Linear ticket → summary file | VM | Amber |
| 2 | Summary → manual test cases | VM | **Green** |
| 3 | Context check: what coverage already exists | VM | **Green** |
| 4 | Decide: new cases, or a scoped regression run | VM | **Green** |
| 5 | Proof the cases | VM | **Green** |
| 6 | Execute on device, and explore | Mac | **Green** |
| 7 | Run the regression suite | Mac | Amber |
| 8 | Report to Testmo and Linear | VM | **Green** with access |

**Two of these become skills we've agreed on:** the **ticket scraper** (stage 1) and the
**context checker** (stage 3). Both are specified below.

---

### Stage 1 — Ticket scraper *(agreed skill)*

**What it does.** Reads the Linear sprint ticket and writes a structured summary to a file. That file
— not the conversation — is what every later stage consumes, which means the work survives a session
ending and a human can correct it in one place.

**Proposed summary fields:**

- What changed, in plain language
- Which area(s) of the app it touches
- **New functionality, or a change to existing code?** — this decides whether we *add* cases on top
  of the scoped pass; it never decides whether we test (see stage 4)
- Platforms affected (Android / iOS / both)
- **Remote-config flag state for the touched area** — recorded every time, including when the answer
  is "none." Most changes aren't flag-gated, but the ones that are will silently invalidate a whole
  case set, so this is a field that gets filled in rather than a question that gets asked when
  somebody remembers
- Risk notes: what nearby behavior could this plausibly disturb?
- Open questions for a human

**Access — the one real question.** Linear is currently proxy-blocked (418), along with every other
API in this workflow.

**The route is the claude.ai Linear MCP connector**, which is already installed. Mechanically it's a
`claudeai-proxy` connector pointed at `https://mcp.linear.app`, authenticated by running `/mcp` and
approving in a browser. The connection still originates from the VM, so the proxy has to allow it.

**How to handle it — the practical path.** The block code is self-documenting. Allow the MCP host,
run `/mcp`, and if the OAuth handshake reaches somewhere else, the next 418 names the exact URL to
add. This converges in a round or two rather than requiring the whole flow mapped in advance:

```
GET  https://mcp.linear.app/*
POST https://mcp.linear.app/*
```

**The caveat worth stating**, because it belongs in the safety conversation rather than being
discovered later: the Linear MCP server exposes write tools (create issue, update issue, comment)
alongside read ones. Allowing the host grants both. The proxy cannot distinguish them — they're the
same host and transport. **The real control is the OAuth scope granted during `/mcp`**, not the
allowlist. That's an argument for the connector over a long-lived personal API key, since OAuth
grants are visible and revocable in Linear, but it means the scope chosen at authorization time is
load-bearing.

**Works today without any unlock:** paste the ticket text into a file. Unglamorous, and it fully
unblocks stages 2–5.

---

### Stage 2 — Manual test cases from the summary

**What it does.** Turn the summary into manual test cases shaped like Testmo's own fields — Case,
Preconditions, Steps, Expected Result, Folder, Suite, Restricted to OS, Configurations.

**With the Testmo MCP, these can be written straight into the case repository** rather than generated
as a CSV and imported — the MCP exposes the case repository directly. That's a real simplification,
and it moves gate 2 from "review before import" to "review before write." Worth noting that this is
the first stage that wants *write* access, which is why §6 proposes starting read-only.

**Rating: Green.** Pure generation, nothing blocked.

**What makes it good rather than plausible.** The failure mode isn't that Claude can't write test
cases; it's that it writes *plausible-looking wrong ones at volume*. Three guards:

- **Ground it in the real corpus.** The full Testmo case repository export is already on disk — 3,624
  actual cases to pattern-match against, with their real Steps and Expected Result conventions. The
  house style doesn't need inventing.
- **Carry the existing authoring rules.** One case covers one thing. Assert only what the case is
  about. Never write a case around a known app bug.
- **Make rejection cheap.** Stage 5 and gate 2 exist because this stage's output needs reading.

**An edge worth naming:** the skill has to know the current remote-config flag state, because the
repo only ever holds the configuration that's live. A skill that doesn't check will confidently write
cases for a configuration that's turned off.

---

### Stage 3 — Context checker *(agreed skill)*

**What it does.** For the area the ticket touches, answer the QA question: **what do we already have,
is it adequate for this change, and what's missing?**

**Rating: Green — and this is the one to build first.** It needs no network: the Testmo repository
export is already local. It depends on no other stage. And it's useful on its own, independent of
whether the rest of this gets built.

**It reads Testmo first.** The official test case repository export —
`shared/Claude-Context/CLAUDE_LOOK_HERE_FOR_OFFICAL_TEST_CASES.csv`, 3,624 cases — carries Folder,
Suite, Steps, Expected Result, Preconditions, State, Restricted to OS and Configurations. That's
enough to answer "what cases cover this area and what do they actually check," which is the QA
coverage question.

**Two structural facts about the corpus, found by reading it, that determine whether the answer is
right:**

- **`Folder` is the area; `Suite` is the iteration.** The same feature reappears under new suite
  names as it gets rebuilt — three variants of "App Navigation / Trip Planner" share folders and
  together hold ~1,176 cases. 64 of 179 folders span multiple suites. Group by folder and an area
  is whole; group by suite and two thirds of its coverage disappears silently.
- **23% of the corpus is retired.** 838 cases are marked "No Longer Valid", and 217 of those are
  marked automated — meaning automated tests may still be running against cases nobody considers
  valid. Retired cases are excluded from coverage counts by default, but reported, because a large
  retired set beside a thin live one is itself a finding.

**Two read paths, and both are worth keeping.** The export is offline, free, instant, and ideal for
broad sweeps across thousands of cases — but it goes stale the moment someone edits a case. The
Testmo MCP reads live, which is better for targeted lookups and for confirming anything the export
implies. Suggested division: **export for breadth, MCP for truth.** Keeping the export path also
means this skill works with no access at all, which is why it's first in the build order.

**Proposed output:**

- Existing cases covering the touched area, with what each actually verifies
- An adequacy read: does this change break any assumption those cases rely on?
- Gaps — what the change implies that nothing currently covers
- Secondary: which of those cases are automated, and which are manual-only

**On that last line — corrected after reading the export.** Testmo tracks automation itself, in two
columns (`Automation` and `Test Case Status`). So answering *whether* a case is automated does not
need the test repo at all. The caveat is different from the one originally assumed: **those two
fields disagree on 285 cases**, so the honest output marks conflicts as unverified rather than
picking a winner.

The dirty-header problem is real but narrower than stated: it only affects *which file* automates a
case, not whether one does. Roughly 123 of 150 Android tests and 25 of 27 iOS tests carry a usable
case ID; some are blank, some are bare numbers, some are duplicated. That limits file-level
traceability. It does not limit the coverage answer.

Cleaning those headers is worth doing — it would also fix the team Google Sheet's sync, which joins
on the same line — but it is **not a blocker for this skill.** The Testmo-side answer stands on its
own.

---

### Stage 4 — New cases, or a scoped run

**What it does.** Decide what this ticket is owed. **It is not a branch between testing and not
testing.**

**The floor is always the same: a scoped pass on the area of the app that changed.** Code moved, so
that area gets looked at — whether the ticket added a feature, upgraded a dependency, or refactored
something that was supposed to behave identically. "No new functionality" is a reason not to write
new cases. It is never a reason to skip the area.

New functionality adds new cases **on top of** that floor; it doesn't replace it.

So the real output of this stage is two lists, one of which is never empty:

| | Always | When there's new functionality |
|---|---|---|
| **Scoped pass** on the changed area — existing cases to re-run, plus exploratory charter | ✓ | ✓ |
| **New cases** for the new behavior | | ✓ |

This is the part of the original outline that's most right and easiest to get wrong: *it's okay not
to always make test cases, but if not, something changed and we need to know what to test instead.*
The failure mode to design against is a ticket classified as "just a refactor" and therefore tested
as nothing — which is exactly the kind of change that breaks things quietly.

**Rating: Green**, largely by reuse — the repo already implements scoped runs driven by an explicit
file list, so the decision output should drop into that existing mechanism rather than inventing a
parallel one.

---

### Stage 5 — Proofing

**What it does.** A second opinion on the generated cases before a human spends attention on them.

**Rating: Green.** A headless Claude instance with its own agent definition gives genuinely fresh
context — better than a sub-agent inside the same session, which inherits the reasoning that produced
the thing it's reviewing.

**The design rule that makes this worth doing at all:** the reviewer gets *the ticket and the cases*
— **not** the reasoning behind them. An agent handed your conclusion tends to come back having
confirmed it. A proofing step that launders the first draft's assumptions is worse than none, because
it manufactures confidence.

**A stronger variant:** have the proofer write cases *independently* from the same summary, then diff
the two sets. The disagreements are where human attention is actually worth spending.

---

### Stage 6 — Execute on device, and explore

This is the stage that makes the loop more than a document generator, and per A3 it's observed
working rather than theoretical. So the question here isn't *whether* — it's how it fits into the
workflow and what its boundaries are.

**The mechanic.** Given a phone, Claude reads the screen (view-hierarchy dump plus an actual
screenshot it can look at), acts on it (tap, swipe, type, deep link, app lifecycle), and re-reads to
verify. Everything below is built on that one loop.

**Three distinct jobs, which want different handling:**

**1. Execute a written case.** Walk the steps from stage 2 or an existing Testmo case. For each step:
locate the target, act, verify the expected result, capture evidence, continue. Output is per-step
pass/fail with screenshots attached — the same shape a human tester's run produces, which is what
makes it reportable in stage 8.

**2. Scoped exploratory.** Seeded with the ticket's area and a charter — *what are we probing for?*
Not "click everything," but "this change touched the load list; what nearby behavior could it have
disturbed?" The reference repos are the ground truth for what the app is *supposed* to do, which is
what separates exploratory testing from random clicking. **Note:** the iPhone reference repo is
available; the Android one isn't currently, and exploratory work on Android wants it.

**3. Whole-app sweep.** Breadth-first across menu destinations, checking each screen loads and
behaves. Lower value per step than scoped exploration, but it catches the things nobody thought to
scope.

**Boundaries — design parameters, not doubts:**

- **Coordinates.** Driving a device this way is inherently coordinate-based, which contradicts the
  standing rule that tests must never use coordinates. Both positions are right in different scopes:
  coordinates are fine for an *ephemeral* session on one known device, and unacceptable in a
  *committed* test that must survive five screen sizes. The rule to write down: **coordinates never
  cross from stage 6 into a committed artifact.**
- **WebViews and custom surfaces are opaque.** A hierarchy dump sees a WebView as roughly one node,
  and custom-drawn surfaces as nothing at all. The PDF viewer, the in-app browser and the map are all
  in this category. They're already hard for the automated suite and they're harder for a crawler,
  which has no prior knowledge to fall back on. Exploratory charters should route around them or
  verify them by screenshot.
- **Capture as you go.** A crawl takes a different path each run, so a finding can't be recovered by
  re-running it. Evidence has to be captured in flight. Anything worth filing needs a *deterministic*
  repro written by hand afterward — the crawl finds it, a human pins it down.
- **Context budget sets crawl length.** Each step costs a screenshot plus a dump, and dumps carry a
  lot of off-screen noise. Filtering to visible elements is what makes long sessions viable. Worth
  measuring on one scoped crawl before promising a whole-app sweep.
- **Test data.** Meaningful runs need a provisioned user with the right configuration. That tooling
  exists, and it needs an API the VM can't reach but the Mac can — another reason this stage lives on
  the Mac.
- **Parallelism** resolves to one session per device. The per-device environment isolation already
  exists in the runner. Cost scales linearly, so this wants a measured number before it's a plan.

---

### Stage 7 — Regression suite

**What it does.** Run the existing automated suite. **No net-new automated tests come out of this
loop.**

**Rating: Amber**, and not about capability — the machinery is mature (parallel execution, retries,
results export, Testmo upload, failure artifacts). Claude's contribution is **selection, not
execution**: deciding which tests the ticket makes relevant.

The gap is the **trigger**. The hub isn't available on demand, so the practical path is a local run
on a device unplugged from it — a human action today.

---

### Stage 8 — Report to Testmo and Linear

**Automated results → Testmo: already built and working.** Nothing to do.

**Manual results → Testmo: the MCP closes what was the biggest gap in this plan.** The existing path
submits *automation* runs; a case Claude executed by hand is not an automation result, and filing it
that way would put it in the wrong lane and distort the automation metrics. The Testmo MCP exposes
runs and results as first-class objects, so manual results can land as manual results.

**Exploratory → Testmo sessions.** The MCP also exposes **sessions**, which is exactly the right
home for stage 6's exploratory work. That's a better fit than anything in the original plan: an
exploratory crawl is a session, not a test run, and Testmo already models the difference.

**Linear sub-issue:** the same MCP connector as stage 1. No additional access beyond what stage 1
already needs.

**Pass, or a write-up.** When a case fails, the output shouldn't be "failed" — it should be the
team's bug report, in the team's template, with evidence attached. The generation is Green; the
template is already well-defined. The judgment of *whether a failure is an app bug or a test problem*
is not, and stays with a human.

---

## 5. Where the humans stay

This is what the original outline is really asking: *figure out the workflow based on where we need
to look at things manually.*

| Gate | Where | Why |
|---|---|---|
| **1. Summary accepted** | After stage 1 | A misread ticket poisons everything downstream, cheaply and invisibly |
| **2. Cases approved** | Before Testmo import | Generated cases are plausible by construction; wrong ones become permanent process debt |
| **3. Device run authorized** | Before stage 6 | Touches real devices, real provisioned users, a real API |
| **4. Outward write approved** | Before stage 8 | Testmo runs and Linear issues are visible to the whole team |

**Gates 1 and 2 are about quality and should relax** as that quality becomes measurable.

**Gates 3 and 4 should stay.** They're not about quality — they're about actions with side effects
outside the sandbox. That distinction is the reason the sandbox exists, and it shouldn't erode just
because the loop is working well.

---

## 6. What we need unblocked

The access story collapses into **one pattern, used twice**: two hosted MCP servers, two OAuth
grants. Both Linear and Testmo publish official hosted MCP servers that Claude Code supports, both
authenticate by OAuth in a browser, and both let you choose the access level at authorization time.

That is a much smaller and more honest ask than a set of API tokens, because an OAuth grant is
visible in the vendor's UI and revocable in one click by someone who isn't Claude.

### The allowlist rules

**Linear publishes a separate read-only endpoint**, which means the proxy *can* enforce read-only
here — not by scoping operations, but by making the writable endpoint unreachable:

```
GET  https://mcp.linear.app/mcp/readonly
POST https://mcp.linear.app/mcp/readonly
```

Deliberately **not** `https://mcp.linear.app/mcp` — that's the read-write endpoint. Leaving it off
the allowlist means that even if the OAuth grant carries write scope, writes cannot leave the
machine. That's defense in depth, enforced at the boundary we control rather than the one we don't.

Plus the Testmo MCP host. The beta endpoint is on a `sembi.com` domain rather than `testmo.com`, and
the exact URL needs to come from Testmo's setup instructions — it couldn't be read from inside the
sandbox, which is a mild illustration of the problem. **Open question worth asking Testmo:** does it
offer a separate read-only endpoint the way Linear does? Its read-only/read-write choice appears to
be made at authorization time, which is a weaker control than a distinct URL.

### The part that matters most — and a correction worth making

There is a natural instinct to scope the allowlist more tightly: to a single project, or a single
milestone, e.g. `https://eleostechnologies.testmo.net/milestones/view/1285`.

**The proxy cannot enforce that, for three structural reasons:**

1. **Wrong host.** The MCP server isn't on `eleostechnologies.testmo.net` at all. Allowlisting a path
   on the web UI's domain doesn't constrain the MCP endpoint, which lives elsewhere.
2. **Wrong layer.** MCP is JSON-RPC over a *single* HTTP endpoint. Every operation — read a case,
   create a run, delete something — is a POST to the same URL. What distinguishes them is the request
   *body*, which a URL allowlist never sees. This is the same structural property that makes GraphQL
   un-scopable at the proxy.
3. **Wrong kind of URL.** `/milestones/view/1285` is a web UI path, not an API path. The milestone is
   a parameter in API calls, not a path segment.

**The principle underneath it:** the proxy is a *network* boundary, not an *authorization* boundary.
It controls where Claude can talk — not what it may say once connected. Milestone scoping is an
authorization question, so it has to be answered by Testmo, not by `allowlist.txt`.

### Where control *can* live — four layers, strongest first

Scope can be limited, just not at the URL-path level for operations. There are four real levers, and
they stack:

**1. The endpoint — proxy-enforced, and the only layer we fully control.**
Where a vendor publishes a distinct read-only endpoint (Linear does), allowlisting only that URL
makes writes network-unreachable regardless of what the grant permits. This is the strongest control
available to us because it doesn't depend on the vendor honoring anything.

**2. The OAuth grant — vendor-enforced.**
Testmo offers read-only vs read-write at setup; Linear has OAuth scopes. Strong when honored.
**Caveat worth taking seriously:** there are reports on other vendors' MCP servers of read-only
scopes still exposing write tools. So **verify rather than assume** — after connecting, list the
tools the server actually advertises and confirm none of them write. That check costs a minute and
should be a standing step whenever a grant changes.

**3. Claude Code's own permission rules — client-side, and the most granular layer.**
Individual MCP tools can be allowed or denied by name in `settings.json`:

```jsonc
"permissions": {
  "allow": ["mcp__testmo__*"],
  "deny":  ["mcp__testmo__delete_case", "mcp__testmo__update_case"]
}
```

Rules evaluate **Deny → Ask → Allow**, so a deny beats a broader allow. There's also a server-level
`deniedMcpServers` list. This is the layer that gets closest to "let it read everything but only
write results," because it operates per tool rather than per host.

**One important interaction to check:** a session running in bypass-permissions mode may not consult
these rules at all. If per-tool control is wanted, the permission mode has to be chosen to match —
otherwise layer 3 is decorative. Worth confirming before relying on it.

**4. Convention and the human gates — soft, but auditable.**
The milestone the skills are told to work within, and the review gates in §5. Not enforcement, but
these are what has actually been load-bearing so far.

**The practical recommendation:** use layers 1 and 2 to make writes impossible during Phase 1, layer
3 to shape what's allowed once write access is granted, and layer 4 throughout. No single layer is
sufficient; together they're a reasonable story to take to a security-minded reviewer.

**The recommendation: start both grants read-only.** Stages 1 through 7 need nothing more — the
context checker, case generation, proofing and device work are all reads plus local files. Only
stage 8, and writing cases into the repository in stage 2, need write access at all.

Then grant write **one system at a time**, after the gates have been exercised on real tickets.
Access expanding as trust is earned is a far better thing to take to the team than asking for
read-write into test management on day one — and it costs almost nothing, because the read-only
phase is where most of the value is anyway.

### Also needed

- The **Android reference repo** alongside the iPhone one, for exploratory ground truth
- Confirmation of which Testmo project/milestone this workflow is scoped to, as a convention the
  skills encode

### What we are deliberately not asking for

**GitHub API access.** GitHub is driven through Desktop and copy-paste by preference and policy, and
the loop doesn't need it. Worth saying out loud: a smaller ask is a more credible one, and it shows
the asks were derived from the work rather than requested speculatively.

---

## 7. Sharing this with the team

The workflow should live as **skills and agent definitions committed inside the repo**, not as
configuration on one laptop. Then cloning gets you the workflow, and changes to it get reviewed like
any other change.

**Sequencing note:** land it in `eleostech/quackium-tests` rather than the personal account the live
checkout still points at. Worth confirming that migration is complete before investing in
repo-resident tooling.

---

## 8. Edges and open questions

**iOS is the weakest leg, by a distance.** There's no equivalent of the Android device-driving path —
an iPhone means Appium and WebDriverAgent, which is heavier and more fragile. There's no iOS install
automation, and the hub has no iOS at all. Honest answer: **iOS rides the regression path only**, and
manual/exploratory automation on iOS is out of scope until the Android version has proven itself.

**The single loop is last, not first.** An orchestrator chaining all eight stages behind one command
is the obvious end state and the wrong thing to build early. Each stage needs to be independently
useful and independently trustworthy first, or the orchestrator just makes failures harder to locate.

**Cost is unmeasured.** Exploratory crawling is the expensive stage, and "test the whole app in
parallel across N devices" has no number attached yet. Measure one scoped crawl before promising it.

**Test-data provisioning is a scaling risk this brings forward.** User provisioning already runs
heavily against a rate-limited external base, with a drafted issue about moving off it. More runs
brings that deadline closer rather than creating a new problem.

**Garbage in.** Stage 3's output is only as good as the Testmo corpus, and stage 2's only as good as
the ticket. Neither stage can detect its own bad input. The gates are the mitigation, which is why
they're load-bearing rather than ceremonial.

---

## 9. Proposed sequencing

**Phase 0 — no unblocks required.** The **context checker** skill first (it needs nothing and is
useful immediately), then the **case-generation** skill, then the **proofing** agent. The ticket
scraper can be built in parallel against pasted ticket text, so it's ready the moment access lands.

**Phase 1 — both MCPs, read-only.** Authorize Linear and Testmo, add the two host rules, iterate on
any follow-up 418s. This alone makes the context checker read live data and the ticket scraper work
end to end. Nothing can be written yet, which makes it a cheap phase to say yes to.

**Phase 2 — the device leg.** Execution and exploratory on the Mac, scoped to one area of the app
before anything broader, with the crawl measured.

**Phase 3 — write access, one system at a time.** Testmo write first (results and sessions are the
higher-value, lower-risk writes), then Linear write for sub-issues. Each only after the gates have
been exercised on real tickets.

**Phase 4 — the remainder.** The orchestrator, then iOS.

---

## 10. What would make this fail

Worth stating plainly, because a proposal that can't describe its own failure mode isn't finished:

1. **Volume without judgment.** 200 plausible test cases nobody has time to read is a net loss. The
   gates prevent this, and only if they're honored.
2. **Automation metrics quietly distorted** by manual results filed through the automation path.
3. **A crawler that finds bugs nobody can reproduce**, because evidence wasn't captured in flight.
4. **Repo-resident tooling built on the wrong repo** while the migration is still in progress.

All four are avoidable. None are avoided by default.
