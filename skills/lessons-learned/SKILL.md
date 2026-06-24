---
name: lessons-learned
description: Evolve the repository CLAUDE.md with lessons learned from merged PRs, debugging sessions, and design decisions
user-invocable: true
argument-hint: "[--ci] [pr numbers | 'scan' [N] | 'verify']"
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Edit", "Task", "WebFetch"]
---

# Lessons Learned

Update the current repository's `CLAUDE.md` with design decisions, performance findings, and non-obvious constraints.

**Arguments:** `{args}`

## Modes

| Input | Action |
|-------|--------|
| *(empty)* | Extract lessons from the current session's work |
| PR references (`615`, `pr 580-616`, `scan`, `scan 30`) | Read specified PRs (or scan recent merged PRs) for undocumented design decisions |
| `verify` | Audit all existing CLAUDE.md claims against actual source code; report as a table |
| `--ci {pr}` | CI mode: headless run on a merged PR reviewed by kaa (see CI Mode below) |

For `verify` mode: check each claim against source, report findings, and fix any inaccuracies. Skip the drafting and writing steps below.

## CI Mode (`--ci`)

Invoked headlessly by kaa after a PR merges. Applies a **higher bar** than interactive mode — no human in the loop to filter proposals, so the skill must be conservative.

### Signal sources

Process **both** of these, then draft entries once:

1. **Human replies to kaa's inline comments** — where the human supplied context kaa couldn't have known from the diff/repo alone
2. **Human-human discussions** (conversation comments) — only where the discussed code was **unchanged at merge** (design explanation, not bug fix)

### Filter chain (all must pass to be CLAUDE.md-worthy)

- The human supplied context **not present** in the diff or repo (not a hallucination correction — kaa misreading code that was right there)
- The claim is **falsifiable**: "we don't validate here because X service guarantees it upstream" ✅ — "this is fine" ❌ — style preferences ❌
- kaa's original finding was **locally valid** — it couldn't have known without the supplied context
- The entry would **prevent a different engineer** from making the same wrong assumption

### Missed bugs (separate signal)

If humans caught a bug in their discussion that kaa missed entirely, do **not** write it to CLAUDE.md. Flag it separately in the PR comment as "I missed: [description]" for manual action.

### Writing

- Process **all** signals first, then write once
- If nothing passes the filter: post "bar not met — nothing written" on the PR and exit without touching CLAUDE.md
- If entries are drafted: run compaction alongside the write (see step 3), commit directly to `main`, post a PR comment with what was written + commit link + any missed bugs flagged
- Commit message: `lessons: update CLAUDE.md from {repo}#{pr}`

### Post PR comment format

```
## Kaa learned from #{pr}

### Added to CLAUDE.md
- {section}: {one-line summary} ([commit](URL))

### Flagged (not written — needs manual action)
- Missed bug: {description}
```

If nothing was written and nothing flagged, post: "Reviewed feedback on #{pr} — bar not met, nothing written."

## Workflow

### 1. Gather context

Read the repo's `CLAUDE.md` to understand existing entries (avoid duplicates).

For PR-based modes, use the gather script to collect PR context (handles GHE hostname detection):
```bash
# Specific PR (repo inferred from cwd):
CONTEXT_DIR=$(~/.claude/skills/lib/gather-pr-context.sh {number})
# Explicit repo:
CONTEXT_DIR=$(~/.claude/skills/lib/gather-pr-context.sh {number} {owner/repo})
```

This produces `$CONTEXT_DIR/metadata.json` (title, body, files) and `$CONTEXT_DIR/diff.patch`. Read `metadata.json` for the PR description and changed files.

For scanning recent PRs, list them first then gather context for candidates:
```bash
source ~/.claude/skills/lib/gh-env.sh && gh pr list --state merged --limit {N} --json number,title,mergedAt --jq '.[] | "\(.number)\t\(.mergedAt[:10])\t\(.title)"'
```

Filter for PRs that answer: "Why is it designed this way?", "Why not the simpler approach?", "Where does time go?", or "What didn't work?"

### 2. Draft entries

For each finding, draft a FAQ-style entry:

- **Header**: A question someone would actually ask when looking at the code
- **Body**: 2-4 sentences covering the decision, the rationale, and what not to do. Include PR reference.

Place in the appropriate section: "Before You Optimize", "Before You Refactor", or "Before You Add a Feature". Create these sections if the repo doesn't have them.

**Before including an entry, verify it:**
- Read the actual source code; do not trust PR descriptions or agent analysis at face value
- Check scope: does the claim apply to all code paths or just one?
- Look for counterexamples in sibling code (e.g., documenting a `__hash__` fix? check other `__hash__` implementations)
- Confirm it belongs in repo CLAUDE.md (team knowledge that prevents harmful refactors or dead-end exploration, not personal workflow or generic best practices)

### 3. Assess compaction

Before adding entries, check if `CLAUDE.md` needs compaction. Signs:
- File exceeds ~10KB (run `wc -c CLAUDE.md`)
- Multiple entries cover related topics that could merge (e.g., two METHOD entries, two entries about the same subsystem)
- Operational data (profiling commands, CPU breakdowns) that belongs in a separate reference file
- Verbose sentence structure that can tighten without losing meaning

**Preserve the cause-and-effect narrative.** "Previously X happened, which caused Y" is what makes entries useful. Someone reading "do not remove the count gate" needs to understand *what went wrong* (buffers grew for hours, 300MB responses froze the UI). Strip filler words and redundant phrasing, but keep the story of what the previous state was and why it broke.

**Preserve empirical measurements.** Baselines, before/after numbers, per-op costs, and speedup ratios are starting points for future optimization (Newton's method needs a good initial guess). When compacting, keep all concrete numbers (e.g., "458ms -> 98ms (6.9x)", "~1,235 ns/op"). These prevent re-profiling work that was already done. Remove the prose around them, not the numbers themselves.

If compaction is warranted, propose it alongside the new entries. Techniques: merge related entries, tighten prose without losing narrative, or break out detailed content. Keep the core decision and rationale in the root `CLAUDE.md`; link to the breakout file for details.

**Where to put breakout content:**

| Content scope | Target | Why |
|---------------|--------|-----|
| Subsystem-specific (e.g., BSV1/BSV2 codec FAQ) | `CLAUDE.md` in the relevant package directory (e.g., `Core/typing/binaryschema/CLAUDE.md`) | Auto-loads when working on those files |
| Cross-cutting reference (e.g., perf history, architecture overview) | `CLAUDE-SUPPLEMENTS/` at repo root | Loaded on demand via links; no single subdirectory owns it |

In both cases, the root `CLAUDE.md` retains a bullet-point summary of key constraints with a link to the breakout file. The breakout gets the full FAQ entries or detailed data.

### 4. Present and write

**Interactive mode:** Show drafted entries (and any compaction proposals) to the user grouped by section, noting verification results. Apply approved changes to CLAUDE.md.

**CI mode (`--ci`):** Skip presentation. Apply all drafted entries directly. Run compaction alongside. Commit to `main`:
```bash
source ~/.claude/skills/lib/gh-env.sh
git config user.name "srv-chippy"
git config user.email "srv_chippy@drwholdings.com"
git add CLAUDE.md
git commit -m "lessons: update CLAUDE.md from {repo}#{pr}"
git push origin main
```
Then post the PR comment (see CI Mode format above) using:
```bash
export GH_HOST && gh api repos/{repo}/issues/{pr}/comments --method POST -f body="..."
```
