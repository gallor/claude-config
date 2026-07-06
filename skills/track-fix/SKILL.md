---
name: track-fix
description: Retroactively track an untracked bug fix or breakage repair with a GitHub issue and a properly named branch. Use this skill whenever work has been done (committed or uncommitted) that fixes a bug, addresses a breakage found during testing, or otherwise resolves a problem that has NO associated GitHub issue yet — especially when the work is sitting on main or on a branch with no ticket number. Triggers on phrases like "track this fix", "this bug isn't tracked", "create a ticket for this work", "I fixed something but there's no issue", or when the user has clearly just repaired something and wants it captured, branched, committed, and pushed. Reach for it before pushing untracked fix work.
---

# Track Fix

Take fix work that has no GitHub issue behind it and make it properly tracked: find or create the issue, put the work on a correctly named branch, commit with an issue reference, and push.

**Perform ALL steps inline in the current agent. Do NOT spawn subagents.** The steps are sequential and each depends on the previous one's result.

## Why this exists

Fixes discovered during testing or in response to breakage often get written directly, with no issue filed first. That work then lands untracked: no ticket explains *why* it changed, and the branch name carries no reference. This skill closes that gap after the fact. The goal is that every fix ends up traceable to an issue and a branch whose name announces which issue it belongs to.

## Process

### Step 1 — Assess the current state

Establish what you're working with before deciding anything:

```bash
git rev-parse --abbrev-ref HEAD          # current branch name
git status --porcelain                   # uncommitted changes
git log --oneline main..HEAD             # commits on this branch (empty if on main / no new commits)
```

Use `main` as the primary branch unless `master` or another default is evident from `git remote show origin`. Note three things: (a) the branch name, (b) whether there are commits ahead of the primary branch, (c) whether there are uncommitted changes. If there is *no* work at all (clean tree, no commits ahead), there is nothing to track — say so and stop.

### Step 2 — Look for an existing ticket number

The work may already belong to an issue even though it wasn't filed as one first. Search two places for an issue number:

- **Branch name** — e.g. `fix/123-widget-crash`, `123-widget-crash`, `bugfix-123`. Extract the numeric token.
- **Commit messages on the branch** — scan `git log main..HEAD` for `#123`, `Fixes #123`, `Closes #123`, or a bare issue number.

If you find a candidate number, go to Step 3. If nothing turns up in either place, go to Step 4 (create a new issue).

### Step 3 — A number was found: verify it on GitHub

Look the issue up (an issue that is **closed still counts** — the work is tracked either way):

```bash
gh issue view <number> --json number,title,state,url
```

- **If the issue does not exist** (the number was a false positive), fall through to Step 4 and create a new issue.
- **If the issue exists**, check whether a PR is already attached to it:

  ```bash
  gh pr list --search "<number>" --state all --json number,title,headRefName,url
  ```

  Also check for a PR that closes the issue via its body/linked references if the search is inconclusive.

  - **A PR is attached** → the work already has a home. Report the issue and the PR's branch name (`headRefName`) and **stop**. Do not create a branch, commit, or push — the user should move their work onto that existing branch themselves, and you shouldn't guess how.
  - **No PR is attached** → report that the issue already exists (with its URL), then continue to Step 5 to name the branch, commit, and push against this existing issue number.

### Step 4 — No ticket: draft and create one

Draft the issue from the actual work, then get approval before creating it.

1. **Understand the change.** Read the diff so the issue describes what really happened:
   - Uncommitted work: `git diff` and `git diff --cached`
   - Committed work: `git diff main..HEAD`

2. **Draft problem + proposed solution.** Follow `rules/github-issues.md` for structure, labels, and conventions. For a fix like this, the reliability/audit shape fits well:
   - **Problem** — what was broken, with `file:line` references, and how it surfaced (e.g. "found during testing of X").
   - **Impact** — what happened, or would happen, in production.
   - **Proposed Solution** — the fix that the diff actually implements, described concretely.

   Prefer a bug-report template if `.github/ISSUE_TEMPLATE/` has one; otherwise use the reliability/audit structure from `rules/github-issues.md`.

3. **Verify labels before using them.** `gh label list` — never pass a label that doesn't exist (`gh issue create --label` fails on unknown labels). Create the label first if it's genuinely needed.

4. **Show the drafted title and body to the user and get confirmation.** This is their chance to adjust wording or labels before anything is filed.

5. **Create the issue** with `gh`:

   ```bash
   gh issue create --title "<title>" --body "<body>" --label "<verified-label>"
   ```

   Capture the returned issue number and URL.

### Step 5 — Put the work on a correctly named branch

The branch name must end in `-<issue#>` so the tracking is visible at a glance.

- **If currently on the primary branch (`main`/`master`):** you cannot rename it. Create a new branch that carries the work off main. Name it from the fix plus the issue number, e.g. `fix-widget-crash-123`:

  ```bash
  git switch -c <slug>-<number>
  ```

  Uncommitted changes follow you onto the new branch automatically. If the fix was already committed on main, move those commits onto the new branch and reset main back (confirm with the user before rewriting main's history).

- **If on a feature branch that lacks the number:** rename it in place, appending `-<number>`:

  ```bash
  git branch -m "<current-name>-<number>"
  ```

  If the branch was already pushed, the old upstream name will need cleaning up on push (Step 6 handles the new upstream; mention the stale remote branch to the user).

- **If the branch already ends in the correct `-<number>`:** leave it as is.

### Step 6 — Commit and push

1. **Draft the commit message** from the diff and **reference the issue** so GitHub links them. Use `Fixes #<number>` (or `Closes #<number>`) in the body. Show the message to the user before committing.

2. **Commit** the work:

   ```bash
   git add -A
   git commit -m "<subject>" -m "<body with Fixes #<number>>"
   ```

   If the work was already committed but without an issue reference, offer to amend the message to add it rather than creating an empty follow-up commit.

3. **Push**, setting upstream for the (possibly new) branch name:

   ```bash
   git push -u origin HEAD
   ```

4. **Report** the final state: issue URL, branch name, and pushed commit. If a branch rename left a stale remote branch, remind the user to delete it (`git push origin --delete <old-name>`).

## Guardrails

- **Never rewrite `main`'s history without explicit confirmation.** Moving already-committed work off main and resetting it is destructive; confirm first.
- **Stop when a PR already exists** for a found issue. Reporting the branch and stopping is the correct outcome, not a failure — inventing a parallel branch would fragment the work.
- **Don't file duplicate issues.** The whole point of Step 2/3 is to avoid creating a second ticket for work that's already tracked. When in doubt about whether a found number is the right issue, show it to the user and ask.
- **Verify labels exist before creating the issue** — an unknown label aborts `gh issue create`.
