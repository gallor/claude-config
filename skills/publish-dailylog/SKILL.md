---
name: publish-dailylog
description: Mirror the local ~/code/dailylog.md work journal to the "Daily Log" Confluence page (https://wiki.drwholdings.com/spaces/~gallor/pages/620331006/Daily+Log). Use this skill whenever the user wants to publish, sync, upload, or push their daily log to the wiki / Confluence — triggers on phrases like "publish my dailylog", "sync the daily log to the wiki", "push my dailylog to Confluence", "update the wiki daily log". Companion to the `dailylog` skill, which writes the local file; this skill publishes it.
user-invocable: true
allowed-tools: ["Read", "Agent"]
---

# Publish Daily Log

Publish the local work journal at `~/code/dailylog.md` to the Confluence page **"Daily Log"** (page id `620331006`, space `~gallor`). This is the companion to the `dailylog` skill: `dailylog` appends to the local file; this skill mirrors that file to the wiki.

## Model choice: Haiku, always

This job is mechanical — read a file, read a page, compare, push if they differ. There is no drafting or judgment involved (the local file is already the finished artifact). So the entire operation is delegated to a **Haiku** subagent to keep it cheap and fast. The main session does essentially nothing except spawn that agent and relay its one-line result.

**Use a `general-purpose` agent pinned to `model: "haiku"` — NOT `@fast-worker`.** The `fast-worker` agent type cannot call MCP tools (its toolset is `Read, Grep, Glob, Bash, Edit, Write, LSP` only), and this job needs the `mcp__wiki__*` Confluence tools. A `general-purpose` agent inherits the full tool set including MCP, and pinning it to Haiku keeps the cost identical to `@fast-worker`.

## Sync model: mirror, skip when identical

- **Source of truth is the local file.** `~/code/dailylog.md` defines what the page should contain. The page is a mirror.
- **If the page body differs from the local file, replace the whole page body** with the local file's markdown (`confluence_update_page` replaces the entire body; it is not an append).
- **If they are already equivalent, do nothing** — no page write, no version bump. Report "already up to date". This keeps the page's version history clean.
- Because it is a mirror, any edits made directly on the Confluence page are overwritten on the next publish. That is intended: edit the local file, not the page.

## The one prerequisite that can fail: wiki auth

The `mcp__wiki__*` tools require the wiki MCP server to be authenticated. Its token expires periodically. If the subagent reports that `mcp__wiki__confluence_get_page` is unavailable or returns an auth error, the fix is **not** something the subagent can do — the main session must run the OAuth flow:

1. Call `mcp__wiki__authenticate` (main session).
2. Give the returned URL to the user to open in a browser.
3. When the user pastes back the `localhost:3118/callback?...` URL, call `mcp__wiki__complete_authentication` with it.
4. Re-spawn the Haiku agent.

Do not try to pre-flight auth from the main session on every run; just spawn the agent, and only fall back to the auth flow if it reports an auth failure.

## Procedure

### Step 1 — Spawn the Haiku publisher

Use the Agent tool with `subagent_type: "general-purpose"` and `model: "haiku"`, `run_in_background: false`. Give it this brief verbatim (it is self-contained):

```
Publish a local markdown file to a Confluence page by mirroring. Follow these steps exactly.

TARGET:
- Local file: /home/gallor/code/dailylog.md
- Confluence page id: 620331006  (title "Daily Log", space ~gallor)

STEPS:
1. Read the local file with the Read tool. If it does not exist or is empty,
   STOP and report "local dailylog.md is missing or empty — nothing to publish".
   Capture its exact text as LOCAL.

2. Read the current page body: call mcp__wiki__confluence_get_page with
   page_id="620331006", convert_to_markdown=true, include_metadata=false.
   Capture the returned content value as REMOTE.
   - If this tool is unavailable or returns an authentication/authorization
     error, STOP immediately and report exactly:
     "WIKI_AUTH_REQUIRED: <the error>". Do not attempt any workaround.

3. Compare LOCAL and REMOTE for equivalence. Ignore differences that are pure
   markdown round-trip noise: leading/trailing whitespace, blank-line count
   between blocks, and trailing spaces on a line. Compare the meaningful
   content (headers and bullet text).
   - If they are equivalent: STOP and report "already up to date — no changes
     pushed". Do NOT call any update tool.

4. If they differ, mirror the local file to the page: call
   mcp__wiki__confluence_update_page with:
     page_id="620331006"
     title="Daily Log"
     content=<the full LOCAL text>
     content_format="markdown"
     version_comment="Sync from local dailylog.md"
   This replaces the entire page body with the local file.

5. Report back concisely:
   - Whether you pushed or skipped.
   - If pushed: which day headers (## lines) and section headers (### lines)
     the local file contains, and the new page version number if the tool
     returned it.
   - If skipped: say why (already up to date).

Do not edit the local file. Do not add commentary to the page. The local file
is the exact source of truth for the page body.
```

### Step 2 — Handle the result

- **Pushed / skipped** → relay the agent's one-line outcome to the user, including the page URL: `https://wiki.drwholdings.com/spaces/~gallor/pages/620331006/Daily+Log`.
- **`WIKI_AUTH_REQUIRED`** → run the auth flow in the "wiki auth" section above, then re-spawn the agent once. If it fails again, report the error to the user rather than looping.
- **"local dailylog.md is missing or empty"** → tell the user to run the `dailylog` skill first; there is nothing to publish.

Keep the final report to the user to one or two lines. The published page is the artifact.
