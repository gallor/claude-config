# GitHub Issues

## Starting Work on an Issue → Worktree, Never the Repo Root

Beginning work on any GitHub issue (a freshly filed one or an already-existing one) must check the work out into an isolated git **worktree**, not the repo root. Use the **`/start-work <number>`** skill: it resolves the issue, derives a `<slug>-<number>` branch, and enters a worktree at `<repo-root>/.claude/worktrees/<branch>` via the `EnterWorktree` tool (the `WorktreeCreate` hook names the branch to match the worktree).

- `create-issue` files the issue and then offers the `/start-work` handoff; it does not auto-enter a worktree (filing for later shouldn't spawn a stray worktree).
- `track-fix` (retroactive) migrates the already-written fix into a worktree by the same route, falling back to an in-place branch only if the user declines or `EnterWorktree` is unavailable.
- For `src/`-layout editable-install repos, set `PYTHONPATH="$PWD/src"` in the worktree rather than re-running `pip install -e .` (see the `cp-git-worktree` skill).
- If `EnterWorktree` is genuinely unavailable, say so explicitly and fall back to an in-place branch — never silently edit issue work in the repo root.

## Tooling: prefer the `git-rw` MCP server

Prefer the `git-rw` MCP tools (`mcp__git-rw__*`) for all issue and PR work: `issue_write` (create/update), `issue_read`, `sub_issue_write`, `add_issue_comment`, `search_issues`, `list_issues`, `list_issue_types`, `get_label`. Fall back to the `gh` CLI only when the MCP server is unavailable for the session, or when an operation has no MCP equivalent (label listing and label creation are the main gaps). Every MCP tool takes explicit `owner`/`repo` params, which replace `gh`'s `--repo owner/repo` flag.

## Labels

- **Always verify labels exist** before using them. Check a single label with `mcp__git-rw__get_label`; list all labels with `gh label list` (no MCP equivalent for listing).
- **Creating a label has no MCP equivalent**, so use `gh label create "name" --description "..." --color "HEXCODE"`.
- Applying a nonexistent label fails: `issue_write` with an unknown label errors, and `gh issue create --label "nonexistent"` fails with exit code 1. Create the label first.

## Sub-Issues (GHE 3.18+)

Use the `/sub-issue <parent-number>` skill to create and link sub-issues.

Prefer `mcp__git-rw__sub_issue_write` (method `add`) to link a child under a parent. The `gh` CLI has no native `--parent` support; if you fall back to `gh`, use the REST API.

### When to Use Sub-Issues

**Use a sub-issue** when:
- The finding was discovered as part of a parent investigation or audit
- It shares context/motivation with the parent — needs the parent to explain *why* it matters
- Completing it contributes toward resolving the parent
- Multiple findings are related by a common theme or scope

**Use a standalone issue** when:
- It stands on its own without needing a parent for context
- It was found independently, not as part of a broader sweep
- It crosses concerns (e.g., a security finding during a reliability audit)

**Cross-repo findings** that directly contribute to the parent's goal should still be sub-issues — file the issue in the dependency's repo (using `--repo`) and link it as a sub-issue to the parent. The sub-issues API uses global numeric IDs, so cross-repo linking works. Only use a standalone issue with a reference when the finding is tangential to the parent's scope.

### Workflow

1. Create the parent issue first (`mcp__git-rw__issue_write`, method `create`)
2. Create the child issues (`mcp__git-rw__issue_write`, method `create`)
3. Link each child under the parent with `mcp__git-rw__sub_issue_write`:
   - `sub_issue_id` is the child's **numeric ID**, not its issue number. Fetch it with `mcp__git-rw__issue_read` (method `get`); it is the `id` field of the response.
   - Call `sub_issue_write` with `method="add"`, `issue_number=<parent number>`, `sub_issue_id=<child numeric id>`.
   - Cross-repo linking works because IDs are global: create the child with the dependency's `owner`/`repo`, then link it under the parent.

**`gh` fallback** (MCP server unavailable):

```bash
# Get the child's numeric ID (not the issue number)
sub_id=$(gh api "repos/{owner}/{repo}/issues/${ISSUE_NUM}" --jq '.id')

# Link as sub-issue: use -F (not -f) to send as integer
gh api "repos/{owner}/{repo}/issues/${PARENT_NUM}/sub_issues" \
  --method POST -F sub_issue_id="${sub_id}"
```

- `-f` sends string values, `-F` sends integers. The sub-issues API requires integer `sub_issue_id`.

## Filing Location

File issues in the repo where the **code** lives, not where it's consumed. If analyzing a dependency from repo A that affects repo B, the issue belongs in repo A.

### Internal Dependency Investigation

When the user asks to investigate an internal dependency (e.g., "check ~/git/chippy for X"):
- Analyze the dependency code in its own repository
- If issues are found, **file them in that dependency's repo** by passing that repo's `owner`/`repo` to `mcp__git-rw__issue_write` (or `gh issue create --repo owner/repo` as fallback)
- Do not file upstream code issues in the downstream consumer's repo
- Link back to the downstream context where relevant (e.g., "affects simple-services apps_up_v2")

## Cross-Repo Audit Issues

When auditing a codebase and findings span multiple repos:
- Create a **parent tracking issue** in the primary repo being audited
- File each finding in the repo that owns the code, passing that repo's `owner`/`repo` to `mcp__git-rw__issue_write` (or `gh ... --repo owner/repo` as fallback)
- If the finding directly blocks the parent's goal, **link it as a sub-issue** (cross-repo linking works — IDs are global)
- If the finding is tangential, create a standalone issue and reference the parent in the body
- Always reference cross-repo issues with `owner/repo#number` syntax in the parent body

## Due Diligence Before Filing

Before filing an issue or opening a PR against an external dependency, exhaust local evidence first. Submitting prematurely wastes the maintainer's time and creates noise.

**Required before filing:**

1. **Include the dependency version** — the server/library version is almost always available (logon response, `--version`, package metadata). An issue without a version is not actionable. This is cheap and non-negotiable.
2. **Verify the symptom on the wire** — log the raw data (bytes, JSON, flags) that triggered the bug before filing a spec-violation claim. A symptom observed in behaviour is a hypothesis; the raw wire value is evidence. This applies specifically to "the server is doing X wrong" claims — not required for every bug report.
3. **Rule out client misinterpretation** — before claiming the server is wrong, consider whether your client could be misreading the data.

**Checking release notes across all versions is not required** — that's not systematically practical and the maintainer is better positioned to answer "was this already fixed?" once you provide the version. File the issue with version + wire evidence; let the maintainer cross-reference.

This mirrors `rules/claims-vs-hypotheses.md`: a symptom is a Hypothesis. Wire evidence + version = enough to file.

## Issue Structure

For bug reports, use the `.github/bug_report.md` template, if existing.
For new features, use the `.github/feature_request.md` template, if existing.
For reliability/audit issues, use this structure:
- **Problem**: What's wrong, with specific file:line references
- **Impact**: What happens in production
- **Proposed Solution**: Concrete fix with code examples where helpful
If neither templates for bugs or features exist, use the structure for reliability/audit issues.
