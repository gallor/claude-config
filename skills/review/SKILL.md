---
name: review
description: Review code changes or summarize issue discussions — supports aspect filtering for PRs (code, tests, simplify, security, perf, docs, compat)
user-invocable: true
argument-hint: "[aspects] [owner/repo#number | number]"
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Task"]
---

# Code Review

Review code changes using specialized agents, or summarize issue discussions.

- **PR or local diff**: Each aspect maps to a specialized review agent. Fetches existing comments to avoid duplicates and offers to post inline comments.
- **Issue**: Summarizes discussion; identifies open questions. No code review agents spawned.

**Arguments:** $ARGUMENTS

## Aspects → Agents

| Aspect | Agent |
|--------|-------|
| `code` | `@code-reviewer` |
| `tests` | `@qa-sentinel` |
| `simplify` | `@code-quality-pragmatist` |
| `security` | `@security-sentinel` |
| `perf` | `@performance-college-sprinter` |
| `docs` | `@technical-doc-writer` |
| `compat` | `@migration-specialist` |

## Workflow

### 1. Parse arguments

Extract from `$ARGUMENTS`: aspects (known keywords + `all`), a number reference (PR or issue), and repo. Bare integer infers repo from cwd.

| Input | Mode | Repo | Aspects |
|-------|------|------|---------|
| *(empty)* | local diff | cwd | `code` |
| `86` | PR #86 | cwd | `code` |
| `Chip/chippy#1234` | PR #1234 | Chip/chippy | `code` |
| `all 86` | PR #86 | cwd | all applicable |
| `code security Chip/chippy#99` | PR #99 | Chip/chippy | `code`, `security` |

**CI mode:** if `--ci` is present in `$ARGUMENTS`, skip the preview step (step 7) and auto-post all valid comments immediately without asking for confirmation.

### 2. Detect type and gather context

**Local diff mode** (no number): run `git diff` variants for changed files, stats, full diff. Proceed to step 3.

**Number provided — detect PR vs issue.** Source `gh-env.sh` first to set `GH_HOST` for GHE, then:
```bash
source ~/.claude/skills/lib/gh-env.sh && gh issue view {number} --repo {repo} --json title,state,body,labels,comments,isPullRequest
```
If `isPullRequest` is true (or `gh pr view` succeeds) → **PR mode**. Otherwise → **issue mode**.

#### PR mode

**Do not run `gh repo view` in the main session** (causes `--hostname` errors on GHE). Pass repo from args if available; omit otherwise:

```bash
CONTEXT_DIR=$(~/.claude/skills/lib/gather-pr-context.sh {pr} [{repo}])
```

Produces under `$CONTEXT_DIR/`:

| File | Contents |
|------|----------|
| `metadata.json` | PR title, body, author, state, files |
| `diff.patch` | Full PR diff |
| `inline.json` | Existing inline review comments |
| `conversation.json` | Existing conversation comments |
| `existing-comment-summary.json` | `{file:line: "user: summary"}` for agent dedup |
| `valid-lines.json` | `{file: [[start, end], ...]}` valid diff line ranges |
| `repo.txt` | `owner/repo` identifier |

Cached at `/tmp/pr-reviews/{repo_slug}-{pr}-{head_sha}/`; self-invalidates on new commits.

**Do NOT read these files in the main session.** Pass `$CONTEXT_DIR` to agents. Only read `metadata.json` in the main session (to determine aspects).

**Lazy cache pruning:** At the start of every `/review` invocation run `bash ~/.claude/skills/lib/prune-pr-cache.sh 2>/dev/null`. Also run `bash ~/.claude/skills/lib/prune-pr-cache.sh {repo} {pr}` after posting an APPROVE review. The user can manually prune with `/review prune`.

**Linked issue context (MANDATORY):** After reading `metadata.json`, scan the PR body for `Resolves #N`, `Fixes #N`, `Closes #N`, `Related to #N`, bare `#N`. If found, **always** fetch:
```bash
ISSUE_CONTEXT_DIR=$(~/.claude/skills/lib/gather-issue-context.sh {issue_number} {repo})
```
Pass `$ISSUE_CONTEXT_DIR/metadata.json` to agents as `issue_context`. This is not optional — a PR that is technically correct but solves the wrong problem (wrong approach, adds a new code path when the fix should be integrated into an existing one) is a more serious failure than a code quality nit. Skipping this check is what causes approach-fit regressions to slip through.

**Cross-repo PR context:** Scan the PR body for `Depends on <url>`, `Requires <url>`, `<owner>/<repo>#<number>`, or bare GHE `/pull/<N>` URLs. For each:
```bash
DEP_DIR=$(~/.claude/skills/lib/gather-pr-context.sh {dep_pr} {dep_repo})
```
Pass only `$DEP_DIR/metadata.json` to agents as `dependency_context` (no token cost for the diff).

Proceed to step 3.

#### Issue mode

```bash
CONTEXT_DIR=$(~/.claude/skills/lib/gather-issue-context.sh {number} [{repo}])
```

Produces `$CONTEXT_DIR/metadata.json` (title, body, state, labels, assignees, comments with `createdAt` and `author`) and `$CONTEXT_DIR/repo.txt`.

Read `$CONTEXT_DIR/metadata.json` and present a summary directly — **do not spawn code review agents**:

```markdown
# Issue Summary — {repo}#{number}: {title}

**State**: open/closed | **Labels**: ... | **Assignees**: ...

## Problem Statement
[Condensed from issue body]

## Discussion Timeline
- **@user1** (date): [position/key point]
- **@user2** (date): [response/counterpoint]

## Open Questions
- [Unresolved questions or decisions]

## Consensus / Decision
- [Converged position, or note competing positions]
```

Ask the user if they want to comment on the issue. **Skip steps 3-7** (PR-only).

### 3. Static analysis pre-checks

Run before agents launch; output is ground truth (agents should not re-check what these tools cover).

```bash
# PR mode — baseRefName from metadata.json:
ANALYSIS_DIR=$(~/.claude/skills/lib/static-analysis.py origin/{baseRefName} {repo_root} "$CONTEXT_DIR")
# Local diff mode:
ANALYSIS_DIR=$(~/.claude/skills/lib/static-analysis.py origin/main {repo_root})
```

Output: `$ANALYSIS_DIR/static-analysis.json` (or `$CONTEXT_DIR/static-analysis.json` if output_dir was passed).

| Tool | Fed to aspect | Skipped when |
|------|---------------|--------------|
| `ruff check` (JSON) | `code` | Not installed or no `.py` changes |
| `ruff format --check --diff` | `code` | Not installed or no `.py` changes |
| `bandit` (JSON) | `security` | Not installed or no `.py` changes |
| `towncrier check` | `docs` (triggers `REQUEST_CHANGES` if `missing: true`) | No `newsfragments/` dir |
| `griffe` | `compat` | `ImportError`/`ModuleNotFoundError` per-package; skipped packages logged so `compat` agent does manual diff review |
| `cargo clippy` (JSON) | `code`, `security` | No `Cargo.toml` or no `.rs` changes; diff-aware (only findings on PR-touched lines) |

**Do NOT read `static-analysis.json` in the main session.** Exception: read the `towncrier` field to determine the review event (step 7).

### 4. Determine aspects

`code` is always included unless explicitly excluded. For `all` mode:

| Aspect | Trigger |
|--------|---------|
| `code` | Always |
| `tests` | Test files changed |
| `docs` | `docs/`, `*.md`, or `newsfragments/` changed |
| `security` | Auth/DB/upload/API code changed, or `.rs` files with `unsafe` blocks |
| `compat` | Public methods/classes removed/renamed/signatures changed; new **required** parameters added to existing functions; deleted files or removed exports; PR title/body mentions "remove", "deprecate", "breaking" |
| `simplify` | 3+ new classes/abstractions, or >200 net lines added to a single file |
| `perf` | Code inside loops, known hot paths, or serialization/deserialization changed; files with benchmark/profile annotations touched |

### 5. Launch agents

- Single aspect: launch sequentially
- Multiple aspects: launch **in parallel** using multiple Task tool calls
- Each agent reviews only their domain

### 6. Triage and aggregate

For each finding, check: (1) contradicts `CLAUDE.md` invariant? (2) proposes reverting an explicit choice? (3) orchestrator has session context the agent lacked? (4) ignores a structural invariant? Read relevant code to verify if needed.

**Approach fit (when linked issue fetched):** Is the PR's strategy proportionate to the root problem? Does it introduce ongoing maintenance burden (pattern lists, heuristics, state machines) for something solvable structurally? Surface as a top-level finding if yes.

**Dismiss** failing findings. Include in a "Dismissed" section with reason so the user can override.

**Resolve `[question]` findings** with at most 1-2 lookups (one `grep`/`rg`, one `Read`). Convert to `[issue]`/`[suggestion]` or dismiss if answerable. Only surface a `[question]` if unresolvable within that budget.

For Python source lookups use:
```bash
~/.claude/skills/review/find-module.sh <module> [<module> ...]
~/.claude/skills/review/find-module.sh --env <env> <module> [<module> ...]
```

Aggregate surviving findings:

```markdown
# Review Summary

## Approach Assessment (when linked issue available)
- **Root problem**: [one-sentence from linked issue]
- **PR's approach**: [what the PR does]
- **Fit**: Proportionate? Simpler alternatives?

## Critical Issues (must fix)
- [@agent] Issue description — `file:line`

## Issues (should fix)
## Suggestions (consider)
## Questions (clarify intent)

## Dismissed (conflicts with project context)
- ~~[@agent] Suggestion~~ — Reason: `CLAUDE.md` documents X

| Aspect | Agent | Findings |
|--------|-------|----------|
```

Omit Approach Assessment if no linked issue was found.

### 7. Preview & post inline comments (PR mode only)

Skip for local diff reviews.

**CI mode** (`--ci` in arguments): skip the preview entirely. Validate line numbers, then immediately post all valid comments. Do not ask for confirmation.

Generate numbered inline comments grouped by file. For concrete code changes, use suggestion syntax (renders "Apply suggestion" button):

````
```suggestion
replacement code here
```
````

Only use when replacement is unambiguous and complete.

**Indicators:** Review: 🟢 `APPROVE` | 🟡 `COMMENT` | 🔴 `REQUEST_CHANGES` — Finding: 🔴 `[critical]` | 🟠 `[issue]` | 🔵 `[suggestion]` | 🟣 `[question]` | ⚪ `[nit]`

Preview format:
```
## 🔴 Review: REQUEST_CHANGES

**Body**: Code review focusing on error handling and API consistency.

---

### src/auth/login.py

1. 🔴 **[critical]** Missing input validation — line 45
   body of comment

2. 🔵 **[suggestion]** Description — lines 78-80
   body of comment (may include ```suggestion block```)
```

User actions:

| Input | Action |
|-------|--------|
| `A` / `all` | Post all comments |
| `1,3,4` | Post only those |
| `E2` | Edit comment 2, re-preview |
| `C` / `cancel` | Post nothing |
| "discard 2" / "2 is intentional" | Remove from list |

**Validate line numbers before posting.** Write comments as JSON, then validate:
```bash
python3 ~/.claude/skills/lib/validate-review-comments.py "$CONTEXT_DIR/diff.patch" /tmp/proposed-comments.json > /tmp/validated.json
```
Outputs `{"valid": [...], "rejected": [...], "warnings": [...]}`. Use `valid` for the review payload; fall back to `gh pr comment` for `rejected`. Show `warnings` (auto-corrections within ±5 lines) before posting.

Read `$CONTEXT_DIR/repo.txt`, source `gh-env.sh`, then post:

```bash
export GH_HOST && gh api repos/{repo}/pulls/{pr}/reviews --method POST --input /tmp/review-body.json
```

**Do NOT use `$GH_HOST_FLAG` with `gh api`** (expands incorrectly). **Do NOT use `-f comments='[...]'`** (sends as string, not array); use `--input`. For multi-line comments, add `start_line`/`start_side`; both `line` and `start_line` must be within the same diff hunk.

**Review event:**

| Event | When |
|-------|------|
| `REQUEST_CHANGES` | Any `[critical]` in posted comments, OR missing newsfragment (towncrier) |
| `APPROVE` | Only nits (typos, formatting, naming, style, broken links) or trivial docs (fixing a docstring typo). Missing docstrings, wrong docstrings, missing type annotations are NOT trivial. |
| `COMMENT` | Everything else: `[issue]`, `[suggestion]`, or `[question]` beyond nits. Includes missing docstrings on public-facing functions (exported via `__all__` or importable without leading underscore from a non-underscore-prefixed module). Functions prefixed `_`, or in `_internal/`/`_*.py` files, are internal; missing docstrings there are nits. |

**Review body:** For `REQUEST_CHANGES`/`COMMENT`, summarize thematically (narrative grouping, not a list of comments). For `APPROVE`, one sentence.

**Do NOT use internal agent names** in text posted to GitHub. Strip `[@agent]` attribution from anything posted; keep it only in the local summary shown to the user.

Prefer inline comments; use review `body` for summary. Fall back to `gh pr comment` only for findings that cannot target a diff line. All `gh` commands must source `gh-env.sh` first.

## Agent Prompts

Each agent prompt must include: domain focus, findings formatted as `file:line` with severity (`critical`/`issue`/`suggestion`/`question`).

**Claims vs Hypotheses discipline (mandatory):** Every finding is a Hypothesis until verified against the actual code. Before reporting a finding:
- Verify it by reading the relevant file/call sites — the diff is not the whole picture
- "This is dead code" → grep for callers first; "this is a bug" → construct the input that triggers it
- Label uncertain findings explicitly: "This *may* cause X if Y" not "This causes X"
- Scale verification to severity: nits don't need proof, `[critical]` findings do
- Never report findings you haven't verified — wrong comments waste the author's time

**Diff interpretation:** Only claim code was *removed* if it appears as a `-` prefixed line. Unchanged lines between hunks are still present. Verify the `-` prefix before claiming deletion.

**Local diff mode:** Include the full diff inline.

**PR mode:** Pass `$CONTEXT_DIR`; instruct agent to read `diff.patch`, `metadata.json`, `inline.json`, `conversation.json`. Also instruct:

- **Valid line targeting**: "Read `valid-lines.json` before proposing inline comments. ONLY target lines listed there. Format: `{file: [[start, end], ...]}`."
- **Existing comment dedup**: "Read `existing-comment-summary.json`. Do not re-raise unless existing feedback is incorrect. Format: `{file:line: 'user: summary'}`."
- **Prior reviews**: "Read `reviews.json`. If it contains prior reviews by `srv-chippy`, this is a re-review — frame the review body as a follow-up (e.g. 'Following up on my earlier review...', 'The previous concerns about X have been addressed...', 'One remaining issue...'). Do not re-summarize the whole PR as if reviewing for the first time."
- **Inline kpop investigation**: When a `[question]` finding arises that cannot be resolved by reading the diff alone, attempt to resolve it before posting — but cap at **5 tool calls** (e.g. one `rg` + one `Read` + one follow-up). If resolved within budget, convert to the appropriate severity. If unresolved, post the `[question]` and follow it immediately with a reply comment: "If you'd like a deeper investigation, comment `/kpop <symptom>` on this PR." The `<symptom>` should be a one-line description of the unresolved question, pre-filled so the user can copy-paste it.
- **Dependency context** (if fetched): "Read `$DEP_DIR/metadata.json`. Use title/body to understand the dependency; do not review its code."
- **Approach fit** (always required when issue context exists): Pass `$ISSUE_CONTEXT_DIR/metadata.json` to `@code-reviewer`. Instruct: Does the implementation address the root problem as stated in the issue? Is the approach proportionate — or does it add a new code path where the fix should be integrated into an existing one? Are there simpler structural alternatives? Surface as a top-level `[critical]` finding if the PR solves the wrong problem or takes a divergent approach from what the issue describes.
- **New required parameters**: "When the diff adds a new required parameter to an existing function or method (i.e., no default value), search the **full codebase** for all call sites of that function — not just the diff. Use `rg` to find every caller. If any call site outside the diff is missing the argument, flag it as `[critical]`."
- **Baseline reading**: Before reviewing changed code, read 2-3 unchanged functions or methods in the same class/module to establish what's normal for this codebase. Pay particular attention to functions that share naming patterns with changed code (e.g. if reviewing `bulk_consumers`, read `bulk_publishers`). Comments like "mirrors X", "equivalent to Y", or "same as Z" are explicit signals to fetch and compare the named counterpart. Divergences from the established pattern are findings; conformance is expected and unremarkable.
- **Silent failure detection**: Flag any error handling that swallows exceptions without logging (`except: pass`, `except Exception: return default`), converts failures to silent defaults, or catches broad exception types without re-raising or surfacing the failure. These are `[issue]` severity — callers can't distinguish "worked correctly" from "failed silently".
- **Test brittleness** (for `@qa-sentinel`): Distinguish tests that verify *behavior* (good — survives refactors) from tests that verify *internals* (brittle — breaks on rename/restructure without the behavior changing). Flag tests that assert on private attributes, mock internal implementation details rather than boundaries, or would break if a function were renamed without changing its behavior.

Agents must not duplicate existing feedback, should build on prior discussions, and note if feedback appears addressed in the current diff.
