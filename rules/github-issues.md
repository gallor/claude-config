# GitHub Issues

## Labels

- **Always verify labels exist** before using them: `gh label list`
- Create missing labels before issue creation: `gh label create "name" --description "..." --color "HEXCODE"`
- `gh issue create --label "nonexistent"` will fail with exit code 1

## Sub-Issues (GHE 3.18+)

Use the `/sub-issue <parent-number>` skill to create and link sub-issues.

The `gh` CLI does not have native `--parent` support. Use the REST API.

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

1. Create the parent issue first
2. Create child issues
3. Link via API:
   ```bash
   # Get the child's numeric ID (not the issue number)
   sub_id=$(gh api "repos/{owner}/{repo}/issues/${ISSUE_NUM}" --jq '.id')

   # Link as sub-issue — use -F (not -f) to send as integer
   gh api "repos/{owner}/{repo}/issues/${PARENT_NUM}/sub_issues" \
     --method POST -F sub_issue_id="${sub_id}"
   ```

- `-f` sends string values, `-F` sends integers. The sub-issues API requires integer `sub_issue_id`.

## Filing Location

File issues in the repo where the **code** lives, not where it's consumed. If analyzing a dependency from repo A that affects repo B, the issue belongs in repo A.

### Internal Dependency Investigation

When the user asks to investigate an internal dependency (e.g., "check ~/git/chippy for X"):
- Analyze the dependency code in its own repository
- If issues are found, **file them in that dependency's repo** using `--repo owner/repo`
- Do not file upstream code issues in the downstream consumer's repo
- Link back to the downstream context where relevant (e.g., "affects simple-services apps_up_v2")

## Cross-Repo Audit Issues

When auditing a codebase and findings span multiple repos:
- Create a **parent tracking issue** in the primary repo being audited
- File each finding in the repo that owns the code, using `--repo owner/repo`
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
