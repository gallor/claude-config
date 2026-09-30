---
name: track-epic
description: Render a live status table of a GitHub epic's sub-issues — issue number, sub-task, rollup state (todo/working/PR/kaa-reviewed/merged), PR number, and which agent (if any) is working each. Use whenever the user wants to track, monitor, or check the status of an epic and its sub-issues. Triggers on "track epic <N>", "status of epic <N>", "how's epic <N> going", "monitor <N>".
user-invocable: true
---

# Track Epic

Scan a GitHub epic's sub-issues and print a one-shot status table. Sub-issues are discovered dynamically via the sub-issues API (cross-repo aware), so this works for any epic, not a hardcoded one.

The heavy lifting is a script (`epic_status.py`, in this skill's directory) that does all the GitHub scanning and renders the table. This skill wraps it: resolve the epic reference, fill in the agent column from live agents, run the script, present the output.

## Step 1 — Resolve the epic reference

From the invocation args, accept any of:
- a bare number `88` → infer the repo from the current directory's git remote,
- `owner/repo#88`,
- a full GHE/GitHub issue URL (`https://.../<owner>/<repo>/issues/88`).

Plus optional explicit agent overrides as trailing `N=Name` tokens (e.g. `88 91="Tortilla 91"`), which win over auto-detection.

Infer the repo from the remote (do **not** use `gh repo view` in the main session — it throws `--hostname` errors on GHE):
```bash
git remote get-url origin
# git@git.drwholdings.com:Chippy/tortilla.git  → Chippy / tortilla
# https://git.drwholdings.com/Chippy/tortilla.git → Chippy / tortilla
```
Strip a trailing `.git`; split the `owner/repo` tail. If the cwd is not a git repo and no `owner/repo#N` was given, ask the user which repo the epic is in.

## Step 2 — Set the gh host

```bash
source ~/.claude/skills/lib/gh-env.sh 2>/dev/null || true
```
`epic_status.py` calls `gh` and inherits `GH_HOST` from the environment.

## Step 3 — Build the agent mapping (best-effort)

There is no programmatic issue→agent link, so agents are inferred from **live agent names** by the user's convention of embedding the sub-issue number in the name (e.g. an agent named `Tortilla 92` → sub-issue 92).

1. Call the **`ListAgents`** tool.
2. For every listed agent whose name contains an integer, emit a `--agent <int>=<name>` argument. Passing numbers that aren't sub-issues is harmless — the script only applies matches.
3. Append any explicit `N=Name` overrides the user gave in the invocation.

If `ListAgents` returns nothing usable, skip this step; the Agent column simply shows `—`.

## Step 4 — Run the scanner and present

```bash
python3 ~/.claude/skills/track-epic/epic_status.py <owner> <repo> <epic> \
  --agent <N>=<name> --agent <N>=<name> ...
```
Present the script's markdown table **verbatim**. If a sub-issue advanced since a previous run this session, add a one-line "changed since last check" note under the table. Do not re-post the table when nothing changed if this was a recurring/loop invocation — say so in one line instead.

## States the table can show

`⬜ todo` (open, no agent, no PR) · `🔨 working` (agent assigned, no PR) · `📝 PR (draft)` / `📥 PR (open)` · `🐍 kaa reviewing…` · `🔵 kaa-reviewed (commented)` / `🔴 kaa: changes-requested` / `🟢 kaa-approved` · `✅ merged`. PR-merge state beats issue-closed; an issue closed with its PR still open shows the live PR state with `· issue closed`.

## Recurring monitor (optional)

For an always-updating monitor rather than a one-shot check, schedule this skill with `CronCreate` (e.g. every 15 min, an off-round minute) or drive it with `/loop`. In that mode, pass **`--quiet-if-unchanged`** to `epic_status.py` so an unchanged epic prints a single `NO_CHANGE …` line (it caches the last state signature per epic under `~/.cache/track-epic/`) and only a real change prints the full table — this keeps the conversation from flooding. The cron prompt should still run Step 3 (`ListAgents` → `--agent` args) so the agent column stays live, then relay: `NO_CHANGE` → that one line only; otherwise the full table. Recurring jobs are session-scoped unless made durable and auto-expire after 7 days. Only set one up when the user explicitly asks for a continuous monitor.
