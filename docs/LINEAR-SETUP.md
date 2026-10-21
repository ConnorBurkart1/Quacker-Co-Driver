# Linear access — setup

Stage C's outstanding half. Read-only, one allowlist line, no browser.

## What we're doing, and why it isn't the obvious thing

Linear gives three independent levers, and two of them are real enforcement:

| Lever | Where it's enforced | Using it? |
|---|---|---|
| **Endpoint** — `/mcp/readonly` only ever exposes read tools | Linear | **Yes** |
| **Credential** — an API key restricted to `Read` and to selected teams | Linear | **Yes** |
| **Claude Code permissions** — `deny` rules on tool names | the client | Not needed yet |

We use the first two together. They're independent, so one being wrong doesn't open the
other — the endpoint can't offer a write tool, and the key couldn't call one if it did.
The third lever only constrains Claude Code, not the token, so it's a guardrail rather
than a boundary. It becomes worth adding if we ever move to `/mcp` for the Stage G
sub-issue write.

**Use an API key, not the OAuth flow.** OAuth 2.1 with dynamic client registration means
an interactive browser sign-in, which this sandboxed VM can't do, and it would need
several more allowlist entries — discovery, registration, token exchange — on top of the
endpoint itself. A bearer key needs exactly one line and no browser.

This also means we are **not** using the claude.ai Linear connector. The server is defined
in this repo, so a clone gets it along with everything else.

## The allowlist ask

```
POST https://mcp.linear.app/mcp/readonly
```

**One line, and POST is not a write.** MCP over Streamable HTTP sends every JSON-RPC
message as a POST body to a single endpoint — `initialize`, `tools/list`, and reading an
issue are all POSTs. The methods carry no meaning in this protocol, which is exactly why
the read-only guarantee has to come from the endpoint and the key rather than from the
proxy. (Contrast Testmo, where method + path *are* meaningful, so `GET`-only is real
enforcement at the network boundary.)

A `GET` line is only needed if the client opens an SSE stream for server-initiated
messages. Start without it; if the connection fails to establish, add it then.

## Creating the key

Linear → Settings → Account → **Security & Access** → Personal API keys → New API key.

1. **Permissions** → "Only select permissions…" → **`Read`** and nothing else.
2. **Team access** → "Only select teams…" → the QA team(s) this loop covers.
3. Copy the key (`lin_api_…`). It's shown once.

Two things that can stop this:

- **Admins can disable member API keys** (Settings → Administration → API → Member API
  keys). If the option isn't there, that's why — and it's a conversation with whoever
  administers the workspace, not a bug.
- **A key never exceeds its creator's access.** So the key sees what you see, minus
  whatever you restricted.

Requests for teams outside the key's scope **error rather than silently filtering**. A
workspace-wide search failing is the scoping working, not a broken setup.

## Wiring it up

`.mcp.json` at the repo root — safe to commit, because the key is never in it:

```json
{
  "mcpServers": {
    "linear": {
      "type": "http",
      "url": "https://mcp.linear.app/mcp/readonly",
      "headers": {
        "Authorization": "Bearer ${LINEAR_API_KEY}"
      }
    }
  }
}
```

**`${LINEAR_API_KEY}` is read from the shell environment, not from our `.env`.** That's a
real difference from the Testmo token: `.env` is parsed by `refresh.py` in Python and the
shell never sees it. So the key goes in the shell profile:

```bash
echo 'export LINEAR_API_KEY=lin_api_...' >> ~/.zshrc      # Mac
```

Or `set -a; source .env; set +a` before launching Claude Code, if you'd rather keep both
secrets in one file. Either way `.env` stays git-ignored and the key never lands in
`.mcp.json` or `.claude/settings.json`.

## Verify before trusting it

Do this once, before the first real ticket:

- [ ] `claude mcp list` shows `linear` connected
- [ ] `/mcp` → **the tool list contains no create/update/delete tools.** This is the check
      that matters. If a write tool appears, the endpoint isn't doing what we think and
      everything above needs revisiting before we use it.
- [ ] Read an issue in an allowed team → succeeds
- [ ] Read an issue in a team the key doesn't cover → **errors.** If it succeeds, the team
      scoping didn't take.
- [ ] `git grep lin_api_` → nothing

The second and fourth are the load-bearing ones: they're what turn "Linear says it's
read-only and team-scoped" into something observed rather than assumed.

## One workspace per key

One auth session is one workspace. That's fine for Eleos, but it means a second workspace
would need its own server entry — not a reconnection.

## Until this lands

The fallback costs only the comments and the links:

```bash
pbpaste | python3 tools/new_run.py QA-276 --ticket -
```

The `ticket-scrape` skill works either way. Filling in the Structured block — which is the
larger half of what this stage buys — needs no network at all.
