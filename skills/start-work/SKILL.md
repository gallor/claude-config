---
name: start-work
description: Begin work on a GitHub issue in an isolated git worktree, never in the repo root. Use this skill whenever the user wants to start, pick up, or begin working on an issue — triggers on phrases like "start work on #123", "let's work on issue 123", "pick up #123", "begin the fix for that issue", or when handed off from create-issue after filing a new issue. Resolves the issue, derives a branch name, and checks the work out into a worktree under .claude/worktrees/.
user-invocable: true
argument-hint: "[issue-number | owner/repo#number | url]"
---

# Start Work

Begin work on a GitHub issue by checking it out into an isolated git **worktree** — never editing in the repo root. The worktree lives at `<repo-root>/.claude/worktrees/<branch>` and its branch is named for the issue, so the work is isolated from the main checkout and from other in-flight jobs.

**Perform ALL steps inline in the current agent. Do NOT spawn subagents.** The steps are sequential and each depends on the previous one's result.

## Why this exists

Starting issue work directly in the repo root mixes it with the working copy, risks clobbering other parallel work, and leaves no clean branch boundary. This skill makes "start work" mean "enter a worktree": one issue → one branch → one worktree directory. It is the entry point both for picking up an already-filed issue and for the handoff from `create-issue` after a new issue is filed.

## Process

### Step 1 — Resolve the issue

Take the issue reference from `$ARGUMENTS` (a bare number `123`, `owner/repo#123`, or a full GHE URL). If none was given, ask which issue to start.

Look it up (source `gh-env.sh` first for GHE), passing `--repo` for cross-repo references:

```bash
source ~/.claude/skills/lib/gh-env.sh 2>/dev/null || true
gh issue view <number> [--repo <owner/repo>] --json number,title,state,url,labels
```

- **Issue does not exist** → stop and tell the user; do not invent a branch.
- **Issue is closed** → surface that and confirm the user still wants to start work before continuing.
- **A PR is already attached** (`gh pr list --search "<number>" --state all --json number,headRefName,url`) → report the existing branch (`headRefName`) and ask whether to enter *that* branch's worktree rather than creating a new one. Do not silently fork a parallel branch.

### Step 2 — Derive the branch name

The branch name must end in `-<number>` so tracking is visible at a glance, matching the `track-fix` convention. Build it from a short kebab-case slug of the issue title plus the number:

```
<slug>-<number>          e.g.  widget-crash-123, add-csv-export-456
```

Keep the slug to a few words (drop filler; lowercase; hyphen-separated). If a branch or worktree for this issue already exists, prefer reusing it (see Step 3).

### Step 3 — Check for an existing branch or worktree

Before creating anything, see whether this issue already has a home:

```bash
git worktree list                                   # existing worktrees
git branch --all --list "*-<number>"                # local/remote branches ending in the number
```

- **A worktree already exists** for this issue's branch → enter it (Step 4 with that path) instead of creating a new one.
- **A branch exists but has no worktree** → pass that exact branch name to `EnterWorktree` (the `WorktreeCreate` hook checks out the existing branch rather than branching anew).
- **Nothing exists** → use the `<slug>-<number>` name from Step 2.

### Step 4 — Enter the worktree

Use the **`EnterWorktree` tool** with `name` set to the branch (`<slug>-<number>`). This session's `WorktreeCreate` hook (`~/.claude/scripts/worktree-create.sh`) creates the worktree at `<repo-root>/.claude/worktrees/<branch>` on a branch named exactly `<branch>`, freshly based on `origin`'s default branch (or checks out the branch if it already exists). The session's working directory switches into the worktree.

- Pass the branch name directly as `name` — do **not** prefix it or pass a path.
- To enter an existing worktree from a prior session, use `EnterWorktree` with `path` set to that worktree directory instead.
- If `EnterWorktree` fails (not a git repo, or hook error), report the failure and fall back to a plain branch (`git switch -c <slug>-<number>`) in place, telling the user the work is in the repo root, not a worktree.

### Step 5 — Handle the `src/` editable-install layout

Many repos here (chippy, core_python, hedwig, crispy, queso, …) use a `src/` layout with an editable install (`pip install -e .`). In a worktree, imports resolve from the **original** checkout's editable install unless overridden. If `src/` exists in the worktree:

```bash
ls src/ 2>/dev/null && export PYTHONPATH="$PWD/src"
```

Prefix every subsequent command that imports the package with `PYTHONPATH="$PWD/src"` (or export it once per shell, as above). Do **not** run `pip install -e .` inside the worktree — that steals the editable link from the original checkout. See the `cp-git-worktree` skill for the full rationale and caveats.

Activate the project's conda env as usual (from the project `CLAUDE.md`, or the `<repo>-dev` convention).

### Step 6 — Report and begin

Report: the issue (number + URL), the branch name, and the worktree path now in effect. Confirm the session is working inside the worktree (`pwd` under `.claude/worktrees/`), then proceed with the actual work there.

## Guardrails

- **Never start issue work in the repo root.** The whole point is isolation; if `EnterWorktree` is unavailable, say so explicitly rather than silently editing in place.
- **Reuse, don't duplicate.** An existing branch/worktree/PR for the issue is the home — enter it rather than forking a parallel branch.
- **Don't `pip install -e .` in the worktree** for `src/`-layout repos; use `PYTHONPATH` (Step 5).
- **Confirm before starting on a closed issue** or on an existing PR's branch.
