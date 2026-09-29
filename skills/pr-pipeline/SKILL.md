---
name: pr-pipeline
description: Spawn a PR Pipeline agent team with code-reviewer and technical-doc-writer as parallel teammates
user-invocable: true
---

# PR Pipeline Team

Create an agent team to review and prepare a PR for the current branch.

## Workflow

### Step 0: Triage diff complexity

Before spawning any teammates, assess the diff size and complexity (`git diff --stat <base>...HEAD`).

Count non-test files and test files separately. **Trivial** = non-test changes <50 lines across 1-2 non-test files AND test changes <150 lines. **Keep threshold in sync with `review/SKILL.md` step 2b.**

**Trivial diff:**
- **Skip `reviewer`** — the lead reviews inline; the diff isn't worth a subagent round-trip.
- **Skip `doc-writer`** — the lead writes the newsfragment directly (check existing fragments in `newsfragments/` for naming conventions and use markdown formatting).
- Still run the **full test-suite gate (step 5.5)** before creating the PR, then proceed to PR creation (step 6). The gate is never skipped, even on the trivial path.

**Non-trivial diff** (exceeds either threshold, or multi-concern, new APIs, architectural changes):
- Spawn the full team as described below.

When in doubt, lean toward spawning `doc-writer` (it knows towncrier conventions) but skip `reviewer` for small diffs.

### Step 0.5: Run static analysis

Run `~/.claude/skills/lib/static-analysis.py <base_ref>` to produce `static-analysis.json`. Pass the output directory to both teammates so they have deterministic findings (ruff lint, ruff format, bandit, towncrier, griffe) as ground truth. Agents skip re-checking what the tools already cover.

For trivial diffs (step 0 fast path), still run the script — the towncrier check determines whether the PR needs a newsfragment, and ruff findings on changed lines should be fixed before PR creation.

### Step 1: Create team

`TeamCreate` with name `pr-pipeline`

### Step 2: Create tasks
   - Task 1 (conditional): "Review diff for code quality, correctness, and inline comments" (assign to `reviewer`)
   - Task 2: "Draft newsfragment and evaluate documentation needs" (assign to `doc-writer`)
   - Task 3: "Address feedback and create PR" (lead owns, blocked by tasks above)

### Step 3: Spawn teammates
   - `reviewer` — `@code-reviewer` with prompt: "Review the diff on the current branch for quality, correctness, and style. Report any over-engineering signals for escalation. Message the lead with findings."
     **Skip if `/review` already ran in this session** (e.g., as part of the `/tdd` pipeline). The review gate has already been passed.
   - `doc-writer` — `@technical-doc-writer` with prompt: "Examine changes on the current branch. If the repo uses towncrier, draft a newsfragment. Evaluate if documentation updates are needed. PR number will be applied later. Message the lead with drafts."

### Step 4: Lead collects results — shut down each teammate as soon as it delivers its findings (don't wait for both to finish before shutting down the first)

### Step 5: Address feedback (if reviewer was spawned)

### Step 5.5: Full test-suite gate (MANDATORY — before every PR, trivial or not)

Before creating the PR, run the project's **entire** test suite and confirm it passes. This is a hard gate: **if any test fails, ABORT PR creation, do not open the PR, and report the failing tests to the user so they can be fixed first.**

- **Run the whole suite, not just the tests for changed files.** A change can break tests in files it never touched (e.g. a capability/enum/schema change breaking an exact-set assertion elsewhere). Running only changed-file tests is exactly how a green-looking branch lands a failing CI job.
- **Use the project's canonical invocation and environment**, matching how CI runs it (from the repo's `CLAUDE.md` / docs) — e.g. `micromamba run -n <env> python -m pytest tests/ -q`, `nox -s tests`, `cargo test`. Activate the right conda/virtual env first.
- **Lint/format/type gates do NOT substitute for this.** `pre-commit` (or equivalent) frequently has **no test hook** — many repos run the tests as a separate CI step — so a green `pre-commit` says nothing about test status. Run the tests explicitly and read the exit code.
- **On failure:** stop here. Report the failing test names + the assertion/error to the user and leave the branch un-PR'd. Do not proceed to step 6.
- This gate applies to the **trivial fast path** (step 0) too — a small diff can still break unrelated tests.

### Step 6: Create PR — description: 3-5 bullet points, user impact focus. Benchmarks in collapsible section if relevant.

### Step 7: Finalize newsfragment (if `doc-writer` drafted one) — apply PR number to the filename

### Step 8: Shutdown team — shut down any remaining teammates, then `TeamDelete`
