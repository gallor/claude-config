---
name: sub-issue
description: Create a GitHub sub-issue linked to a parent issue
user-invocable: true
argument-hint: <parent-issue-number>
allowed-tools: Bash(gh *)
---

# Create Sub-Issue

Create a GitHub sub-issue linked to parent issue #$ARGUMENTS.

## Workflow

1. **Gather info** from the user (or prior context) for the sub-issue:
   - Title
   - Body (Problem / Impact / Proposed Solution)
   - Labels

2. **Verify labels exist** before creating the issue:
   ```sh
   gh label list --limit 100
   ```
   If any label doesn't exist, create it with `gh label create`.

3. **Create the child issue:**
   ```sh
   gh issue create --title "..." --label "..." --body "$(cat <<'EOF'
   ...
   EOF
   )"
   ```

4. **Link as sub-issue** using the REST API (GHE 3.18+):
   ```sh
   # Get the child's numeric ID (NOT the issue number)
   sub_id=$(gh api "repos/{owner}/{repo}/issues/${CHILD_NUM}" --jq '.id')

   # Link to parent — use -F (integer), not -f (string)
   gh api "repos/{owner}/{repo}/issues/$ARGUMENTS/sub_issues" \
     --method POST -F sub_issue_id="${sub_id}"
   ```

5. **Report** the created issue URL and confirm the linkage.

## Important

- Use `-F` (not `-f`) for `sub_issue_id` — the API requires an integer, not a string.
- File the issue in the repo where the **code** lives. If the parent is in a different repo, use the `--repo owner/repo` flag on both `gh issue create` and `gh api`.
- When creating multiple sub-issues, create them all first, then link them all in a batch.
