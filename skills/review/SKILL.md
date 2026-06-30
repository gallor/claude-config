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

**Linked issue context (MANDATORY):** After reading `metadata.json`, scan the PR body for `Resolves #N`, `Fixes #N`, `Closes #N`, `Related to #N`, bare `#N`, and cross-repo references `owner/repo#N` or full GHE issue URLs. If found, **always** fetch — passing the repo explicitly for cross-repo references:
```bash
# Same-repo issue:
ISSUE_CONTEXT_DIR=$(~/.claude/skills/lib/gather-issue-context.sh {issue_number} {current_repo})
# Cross-repo issue (owner/repo#N or full URL):
ISSUE_CONTEXT_DIR=$(~/.claude/skills/lib/gather-issue-context.sh {issue_number} {issue_repo})
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

### 2b. Size triage

Run `git diff --stat` to assess diff size. **Keep threshold in sync with `pr-pipeline/SKILL.md` step 0.**

Count non-test files and test files separately. **Trivial** = non-test changes <50 lines across 1-2 non-test files AND test changes <150 lines. If either threshold is exceeded: non-trivial.

**Trivial diff:**
- Skip subagents — main session applies the `code` review checklist inline (fast, no round-trip overhead)
- Still run static analysis (step 3) for towncrier and lint findings

**Non-trivial diff:**
- Spawn agents as normal (steps 4-5)

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
| `griffe` | `compat` | `ImportError`/`ModuleNotFoundError` per-package; skipped packages logged. When griffe is unavailable, `compat` agent uses this fallback checklist: (1) removed exports — symbols in `__all__` or top-level that no longer exist; (2) renamed public functions/classes; (3) changed signatures — removed parameters, changed types, required→optional or vice versa; (4) new required parameters on existing functions; (5) deleted files. Flag each as `[critical]` if confirmed external consumers exist (see external consumer check). |
| `cargo clippy` (JSON) | `code`, `security` | No `Cargo.toml` or no `.rs` changes; diff-aware (only findings on PR-touched lines) |

**Do NOT read `static-analysis.json` in the main session.** Exception: read the `towncrier` field to determine the review event (step 7).

### 4. Determine aspects

`code` is always included unless explicitly excluded. For `all` mode:

| Aspect | Trigger |
|--------|---------|
| `code` | Always |
| `tests` | Test files changed; OR the diff adds a new public function/class/method in a non-test file with no corresponding change to any test file |
| `docs` | `docs/`, `*.md`, or `newsfragments/` changed; OR the diff contains added/modified docstrings in Python source files (lines starting with `+` that contain `"""` or `'''`). Agent checks docstrings against the repo's declared convention (Google/NumPy/etc. from `pyproject.toml` or `CLAUDE.md`). |
| `security` | Auth/DB/upload/API code changed, or `.rs` files with `unsafe` blocks |
| `compat` | A `removal` or `deprecated` newsfragment exists for this PR; OR the diff touches a symbol that is in `__all__` (if defined); OR the diff touches a non-underscored symbol in a non-underscored module that has no `__all__`; OR a new **required** parameter is added to an existing function. Do NOT spawn based on title/body keyword matching — too many false positives. |
| `simplify` | 3+ new classes/abstractions; OR >200 net lines added to a single non-test file; OR >200 net lines added to a test file AND any single test function in the diff exceeds ~50 lines (large test count is fine, large individual test functions are not) |
| `perf` | Serialization/deserialization code changed; files in `benchmarks/` or with benchmark/profile annotations touched; PR title/body mentions "performance", "hot path", "critical path", or "latency". "Known hot paths" documented in `CLAUDE.md` also trigger it — see below. |

### 5. Launch agents

- Single aspect: launch sequentially
- Multiple aspects: launch **in parallel** using multiple Task tool calls
- Each agent reviews only their domain
- **Wait for all agents to complete before proceeding to step 6.** Do not begin triage while any agent is still running — contradiction detection requires the full set of findings.
- **Timeout:** after 10 minutes, proceed with whatever findings have arrived. Note timed-out agents in the review body: "⚠️ The following aspects timed out and may be incomplete: [list]."
- **User override:** if the user explicitly says to proceed early (e.g. "just go", "don't wait"), apply the same treatment — triage with available findings and note pending agents. If a late-arriving agent surfaces a conflict after the review is already posted: edit `/tmp/proposed-comments.json` to add the corrected finding, validate line numbers, and PATCH the posted review via the GitHub API — do not refetch the review.

### 6. Triage and aggregate

**Contradiction detection (before anything else):** Scan all agent findings for pairs that touch the same symbol, file:line region, or design decision with opposing recommendations (e.g. "tighten this signature" vs "keep `*args, **kwargs`", "remove this parameter" vs "this parameter is required"). For each contradiction:

1. Identify the constraint each agent was reasoning from
2. Determine which constraint is binding — a factual constraint (existing callers, declared types, test coverage) takes precedence over a stylistic preference (cleaner API surface, stricter typing philosophy)
3. Resolve to a single recommendation; dismiss the weaker finding with an explanation
4. Never post both sides of a contradiction — a reviewer who flip-flops in the same review session erodes trust
5. **Severity disagreements** (two agents flag the same issue at different severities): take the more severe rating. The author can push back during preview if they disagree.

Canonical example: one agent recommends removing `*args, **kwargs` from a public function for a cleaner API surface (stylistic preference); another finds existing callers passing those kwargs (factual constraint). The factual constraint wins; the tightening recommendation should be dismissed before posting.

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

**CI mode** (`--ci` in arguments): skip the preview entirely. After triage, dedup all surviving findings against prior reviews and comments from any non-`srv-chippy-mindloom` reviewer (inline and body). If nothing survives dedup → skip posting entirely and log "no new findings after dedup." If findings survive → validate line numbers and post immediately. Do not ask for confirmation. **If a tool call fails due to permissions, do not ask the user to grant permissions — output the full review summary to stdout and exit. Never prompt interactively in CI mode.**

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
| "don't dismiss 1" / "include 1" | Move dismissed finding back into the post list before posting |

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
| `REQUEST_CHANGES` | Any `[critical]` finding (inline or body), OR missing newsfragment (towncrier). `[critical]` means the bug produces wrong output, data corruption, or a crash — or unintentional public API breakage on a library surface (no removal newsfragment). Style issues, missing tests for already-covered behavior, and non-blocking design concerns are never `[critical]`. |
| `APPROVE` | No `[issue]`, `[question]`, or `[critical]` in any finding (inline or body) — only nits and suggestions at most. Review body: "LGTM, no findings." or one sentence summarising what was reviewed. |
| `COMMENT` | Any `[issue]`, `[suggestion]`, or `[question]` finding (inline or body), beyond nits. Includes missing docstrings on public-facing functions (exported via `__all__` or importable without leading underscore from a non-underscore-prefixed module). Functions prefixed `_`, or in `_internal/`/`_*.py` files, are internal; missing docstrings there are nits. |

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

**Bug classification and confidence gate:** When you identify a potential correctness concern, classify your confidence before deciding how to surface it:

| Confidence | Signals | Action |
|-----------|---------|--------|
| **High** | Can construct the triggering input directly from the diff; produces wrong output, data corruption, or crash | Post as `[critical]` immediately — no kpop needed |
| **High** | Real bug but survivable (wrong but detectable, edge case, or non-crash degradation) | Post as `[issue]` immediately |
| **Medium** | Plausible but requires tracing call sites, checking invariants, or understanding caller guarantees | Run inline kpop (5 tool cap) to confirm before surfacing |
| **Low** | Something feels wrong but you can't articulate the triggering condition | Post as `[question]` + suggest `/kpop <symptom>` |

High-confidence bugs (syntactic, obvious) do not need falsification — posting them directly is correct and efficient. Medium-confidence bugs (semantic, requires tracing) benefit most from the inline kpop cycle. Low-confidence suspicions should not be posted as bugs — escalate to the user instead.

**Diff interpretation:** Only claim code was *removed* if it appears as a `-` prefixed line. Unchanged lines between hunks are still present. Verify the `-` prefix before claiming deletion.

**Local diff mode:** Include the full diff inline.

**PR mode:** Pass `$CONTEXT_DIR`; instruct agent to read `diff.patch`, `metadata.json`, `inline.json`, `conversation.json`. Also instruct:

- **Valid line targeting**: "Read `valid-lines.json` before proposing inline comments. ONLY target lines listed there. Format: `{file: [[start, end], ...]}`."
- **Existing comment dedup**: "Read `existing-comment-summary.json` before finalising any finding. Format: `{file:line: 'user: summary — url'}`. Ignore entries from `srv-chippy-mindloom`; treat all other entries (human reviewers and `srv-chippy`) as prior art. For every finding you plan to post, check for prior comments in two ways:
  1. **By file:line key** — exact match on the same location.
  2. **By symbol name** — search the comment *values* for the symbol name your finding concerns (function name, class name, parameter name). A `.py` and its `.pyi` stub discuss the same symbols; a prior comment on `__init__.py:dumps` is prior art for a finding on `__init__.pyi:dumps` even though the file:line keys differ.

  If a prior comment touches the same symbol:
  - Ask: is my finding *compatible*, *reinforcing*, or *contradicting*?
  - If compatible or reinforcing: proceed normally.
  - If contradicting: resolve before posting — do not post both sides. Determine which is correct by checking the specific factual constraint each relies on (callers, declared types, test coverage, CLAUDE.md invariants, or an explicit author statement in the PR conversation). An author reply explaining a design choice is a factual constraint — do not contradict it with a stylistic preference. Then either: (a) dismiss your finding if the prior one holds, or (b) post a reversal opened with '↩️ Reversing [permalink]. Reason: [specific factual constraint the prior finding missed].' The permalink is the `— https://...` suffix in each entry.

  Never post a finding that contradicts prior feedback without resolving the contradiction first. Unresolved contradictions force the author to do the reasoning you should have done."
- **Prior reviews**: "Read `reviews.json`. If it contains prior reviews (from any reviewer other than `srv-chippy-mindloom`), this is a re-review — frame the review body as a follow-up (e.g. 'Following up on my earlier review...', 'The previous concerns about X have been addressed...', 'One remaining issue...'). Do not re-summarize the whole PR as if reviewing for the first time."
- **Inline kpop investigation**: When a `[question]` finding arises that cannot be resolved by reading the diff alone, attempt to resolve it before posting — but cap at **5 tool calls** (e.g. one `rg` + one `Read` + one follow-up). If resolved within budget, convert to the appropriate severity. If unresolved, post the `[question]` and follow it immediately with a reply comment: "If you'd like a deeper investigation, comment `/kpop <symptom>` on this PR." The `<symptom>` should be a one-line description of the unresolved question, pre-filled so the user can copy-paste it.
- **Dependency context** (if fetched): "Read `$DEP_DIR/metadata.json`. Use title/body to understand the dependency; do not review its code."
- **Approach fit** (always required when issue context exists): Pass `$ISSUE_CONTEXT_DIR/metadata.json` to `@code-reviewer`. Instruct: Does the implementation address the root problem as stated in the issue? Is the approach proportionate — or does it add a new code path where the fix should be integrated into an existing one? Are there simpler structural alternatives? Surface as a top-level `[issue]` finding if the PR solves the wrong problem or takes a divergent approach from what the issue describes. Only escalate to `[critical]` if the divergence makes the stated problem *worse* (e.g. introduces a new data-corruption risk while claiming to fix one). Then apply a **user-experience lens** if the PR touches anything with UX considerations — this includes: output a human reads (notifications, CLI, dashboards), public API surface a caller depends on (new/changed methods, classes, parameters), or an issue that describes a user-visible symptom. When the UX lens applies, ask: does the after-state meaningfully improve the experience, or does it merely fix the mechanism that produced the symptom? For public API changes, also ask: is the design ergonomic for callers — naming, defaults, required vs optional, composability? Skip the UX lens for pure internal bugfixes where no user-facing surface is touched.
- **New required parameters**: "When the diff adds a new required parameter to an existing function or method (i.e., no default value), search the **full codebase** for all call sites of that function — not just the diff. Use `rg` to find every caller. If any call site outside the diff is missing the argument, flag it as `[critical]`."
- **External consumer check** (for `@migration-specialist`): "Before escalating any API-change finding to `[issue]` or higher, verify the symbol has external consumers. Run `gh search code \"{symbol}\" --owner {org}` and filter out the current repo. Treat results as a lower bound — token access may not cover all repos, so no results means 'no consumers found in accessible repos', not 'definitely no consumers'. If results found: escalate to `[issue]` or higher. If no results: downgrade to `[suggestion]` with note 'no external consumers found in accessible repos.' For Python specifically, apply the convention hierarchy as a pre-filter before running the search: underscored module (`_foo.py`) or underscored class → skip search, treat as internal. Symbol absent from `__all__` when `__all__` is defined → skip search, treat as internal. Only run the search for symbols that pass this pre-filter. **Run all searches concurrently** — do not wait for one to complete before starting the next."
- **Baseline reading**: Before reviewing changed code, read 2-3 unchanged functions or methods in the same class/module to establish what's normal for this codebase. Pay particular attention to functions that share naming patterns with changed code (e.g. if reviewing `bulk_consumers`, read `bulk_publishers`). Comments like "mirrors X", "equivalent to Y", or "same as Z" are explicit signals to fetch and compare the named counterpart. Divergences from the established pattern are findings; conformance is expected and unremarkable.
- **Suspected hot path detection** (for `@performance-college-sprinter`): If you identify a code path that *appears* performance-sensitive (tight loops, high call frequency, allocation in critical sections, serialization bottlenecks) but it is NOT already documented in `CLAUDE.md` as a known hot path, flag it as a `[suggestion]` in the review AND append it as a JSON entry to `/tmp/claude_proposed_hotpaths.json` (create if absent): `{"symbol": "...", "file": "...", "reason": "..."}`. Do not ask the user inline — the main session handles confirmation after posting (see step 7 postscript).
- **Untested public surface**: If the diff adds a new public function, class, or method (non-underscored, non-test file) with no corresponding change to any test file, flag it as `[suggestion]`: "New public surface with no test coverage." The `tests` aspect will dig deeper if spawned; this ensures it's surfaced even when only `code` runs.
- **Silent failure detection**: Flag any error handling that swallows exceptions without logging (`except: pass`, `except Exception: return default`), converts failures to silent defaults, or catches broad exception types without re-raising or surfacing the failure. These are `[issue]` severity — callers can't distinguish "worked correctly" from "failed silently".
- **Test brittleness** (for `@qa-sentinel`): Distinguish tests that verify *behavior* (good — survives refactors) from tests that verify *internals* (brittle — breaks on rename/restructure without the behavior changing). Flag tests that assert on private attributes, mock internal implementation details rather than boundaries, or would break if a function were renamed without changing its behavior.

Agents must not duplicate existing feedback, should build on prior discussions, and note if feedback appears addressed in the current diff.

### 7b. Hot path confirmation (after posting, interactive mode only)

Skip entirely in `--ci` mode — no user is present to confirm.

After posting the review, check if `/tmp/claude_proposed_hotpaths.json` exists and is non-empty. If so, present a confirmation table:

```
Suspected hot paths found during review — confirm to add to CLAUDE.md:

| # | Symbol | File | Reason |
|---|--------|------|--------|
| 1 | pack() | encoder.pyx | tight loop, allocation per call |
```

User confirms all (A), some (1,2...), or none (N). Write only confirmed entries to the repo's `CLAUDE.md` under a "Known Hot Paths" section (create if absent). Then delete `/tmp/claude_proposed_hotpaths.json`.
