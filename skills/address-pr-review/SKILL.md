---
name: address-pr-review
description: Address PR review comments — read reviewer feedback, build a plan to fix each comment, apply fixes, push, and respond on GitHub. Use this skill whenever the user wants to address, handle, respond to, or work through PR review comments, reviewer feedback, or requested changes. Also trigger when the user says things like "let's go through the review", "fix the review comments", "address the feedback", or "what did the reviewer say".
user-invocable: true
argument-hint: "[url | owner/repo#number | number]"
allowed-tools: ["Bash", "Read", "Edit", "Write", "Skill", "Task"]
---

# Address PR Review

Read review comments on a pull request, build a plan to address each one, get the user's sign-off on the plan, apply fixes, commit, push, and respond to each comment on GitHub appropriately.

**Arguments:** `$ARGUMENTS` — an optional PR reference (`url`, `owner/repo#number`, or bare `number`). When empty, the PR for the current branch is used.

> **Related skills.** For *just* the outstanding to-do list (no fixing), use `/read-pr` — it returns a deduplicated, thread-grouped action list. To generate a *fresh* critique of the diff (the inverse direction — you reviewing, not you responding), use `/review`. This skill is the "respond to a review someone left you" workflow: plan → apply → push → reply/resolve.

## Phase 1: Gather Review Comments

### Identify the PR

If `$ARGUMENTS` contains a PR reference, use it. Otherwise determine the PR for the current branch (source `gh-env.sh` first so this works on GitHub Enterprise hosts):

```bash
source ~/.claude/skills/lib/gh-env.sh
gh pr view --json number,url,title,reviews,reviewRequests
```

If no PR is found, tell the user and stop.

### Fetch all review context

Use the shared context helper — it fetches every feedback source in parallel, is GHE-aware, and caches by head SHA so re-reads are instant:

```bash
source ~/.claude/skills/lib/gh-env.sh
CONTEXT_DIR=$(~/.claude/skills/lib/gather-pr-context.sh {pr} [{repo}])
```

Pass `{repo}` explicitly when you parsed it from a URL or `owner/repo#number`; omit it for the current-branch case (the helper infers it from cwd). This writes to `$CONTEXT_DIR/`:

| File | Contents |
|------|----------|
| `metadata.json` | PR title, author, state, base/head refs |
| `inline.json` | `[{path, line, body, user}]` — line-anchored comments |
| `conversation.json` | `[{body, user}]` — general PR comments |
| `reviews.json` | `[{user, state, body, submitted_at}]` — review summaries (humans and bots) |

You also need the **REST comment IDs** (for replies) and **GraphQL thread IDs** (for resolution), which the helper's summaries drop. Fetch them directly — these must be GHE-aware, so keep `GH_HOST` exported from the sourced `gh-env.sh`:

```bash
gh api repos/{owner}/{repo}/pulls/{number}/comments   # includes .id and .in_reply_to_id
```

(Thread IDs for resolution are fetched in Phase 5 via GraphQL.)

Collect every comment from every reviewer. For each, capture: who left it; whether its review requested changes, approved, or just commented; the file and line(s); the comment text; the comment ID; and whether it's already resolved.

**Skip threads that are already resolved — only work on open threads.** This skill may be invoked multiple times against the same PR (e.g., after a second round of review), so it should always reflect the current state of the review, not replay work that's already been done. **Silence is not resolution:** a nit or optional suggestion with no author reply is still open.

### Read the relevant code

For each comment, read the file and lines it references so you understand the current state of the code. This context is essential for building a good plan.

## Phase 2: Build the Plan

For each open review comment, draft a plan entry with:

- **The reviewer's comment** — quoted verbatim
- **File and location** — where the comment applies
- **Your proposed action** — one of:
  - **Accept as-is**: the suggestion is clear and unambiguous — apply it directly
  - **Accept with interpretation**: a valid point, but the fix requires a judgment call — explain what you'd do and why
  - **Needs user input**: the reviewer invited the author to decide, or the right fix is genuinely ambiguous — flag for the user
  - **Disagree / question**: you think the suggestion might be wrong or counterproductive — flag so the user can decide whether to push back

For "Accept as-is" items, describe the specific change you'll make. For everything else, explain the options and what you'd recommend.

### Present the plan

Present the full plan to the user in a clear format. Group comments by reviewer and file. For each entry, show the reviewer's comment, your proposed action, and — for ambiguous cases — the options you see.

Example format:

```markdown
## Review from @reviewer-name (requested changes)

### 1. src/foo.py:42 — Missing null check
> "This will blow up if `bar` is None"
**Action:** Accept — add `if bar is None: raise ValueError("bar required")`

### 2. src/foo.py:78 — Consider using dataclass
> "This dict-based approach is getting unwieldy, might be worth a dataclass"
**Action:** Needs your input — the reviewer is suggesting but not requiring this.
Options:
  a) Convert to a dataclass (cleaner but touches more files)
  b) Keep as-is and explain why in a reply
  c) Something else?
```

Then ask the user for their input on items that need it, and for sign-off on the overall plan. Iterate until the user says the plan is good.

## Phase 3: Apply Fixes

Once the user approves the plan, apply all the code changes. Work through them methodically — don't rush. After applying all fixes:

- Run any linting / pre-commit hooks if the repo has them (check for `.pre-commit-config.yaml`)
- Fix any issues that come up from linting

## Phase 4: Commit and Push

### Write the commit message

Invoke the `write-commit-msg` skill (via the Skill tool) if it's available. If it isn't, write a commit message following this template:

```
Address PR Review Feedback

- <standalone description of change 1>
- <standalone description of change 2>
- ...

Co-Authored-By: <model attribution>
```

Each bullet should make sense on its own when reading `git log` — describe what changed and why, without referencing the review or reviewer. Someone reading the git history shouldn't need to find the PR to understand what happened.

- Good: `- Add null check for bar in process_request() to prevent AttributeError on optional input`
- Bad: `- Fixed the thing @alice pointed out`
- Bad: `- Addressed review comment about null check`

Stage only the files you changed, commit, and push:

```bash
git add -u
git push
```

If there are new files, stage them explicitly by name. **Never use `git add -A` or `git add .`.**

## Phase 5: Respond to Comments on GitHub

For each review comment, respond on GitHub based on how it was addressed. All `gh` calls in this phase must source `gh-env.sh` first (GHE support), and `gh api` should use an exported `GH_HOST` rather than `$GH_HOST_FLAG` (which expands incorrectly):

```bash
source ~/.claude/skills/lib/gh-env.sh
export GH_HOST
```

### Accepted as written
Resolve the thread without commenting — the code change speaks for itself.

```bash
gh api graphql -f query='mutation { resolveReviewThread(input: {threadId: "<thread_id>"}) { thread { isResolved } } }'
```

### Accepted with modifications
Reply explaining what you did and why it differs from the literal suggestion, then resolve the thread.

```bash
gh api repos/{owner}/{repo}/pulls/{number}/comments/{comment_id}/replies -f body="<explanation>"
```

Then resolve the thread with the `resolveReviewThread` mutation above.

### Not addressed
Leave the thread open. Do not resolve it. Do not comment unless the user specifically wanted to say something.

### User disagreed or questioned
Reply with the user's reasoning but do **not** resolve the thread — leave it open for the reviewer to respond.

### Getting thread IDs for resolution

The REST API comment IDs and GraphQL thread IDs are different. To resolve threads you need the GraphQL node IDs. Fetch them with:

```bash
gh api graphql -f query='query {
  repository(owner: "{owner}", name: "{repo}") {
    pullRequest(number: {number}) {
      reviewThreads(first: 100) {
        nodes {
          id
          isResolved
          comments(first: 1) {
            nodes {
              body
              path
              line
            }
          }
        }
      }
    }
  }
}'
```

Match threads to your plan entries by file path, line number, and comment body content.

## Phase 6: Re-request Reviews

After all comments are addressed and responded to, check which reviewers left "changes requested" reviews. If you've addressed all of their comments, re-request their review.

`gh pr edit` fails in our GHE environment (broken GraphQL mutation — see `rules/command-line.md`), so use the REST API. Keep `GH_HOST` exported from the sourced `gh-env.sh`:

```bash
OWNER_REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
gh api "repos/${OWNER_REPO}/pulls/{number}/requested_reviewers" -f "reviewers[]={reviewer}"
```

Only re-request from reviewers whose feedback was fully addressed (all their threads resolved or replied to). If any of their comments were left open intentionally, do not re-request — the user probably wants to discuss further before asking for another look.

## Important Notes

- Always get user sign-off on the plan before making any code changes.
- When in doubt about a reviewer's intent, ask the user rather than guessing.
- Never resolve a thread where the user disagreed with the reviewer.
- If a reviewer comment doesn't require a code change (e.g., a question or a "nit" the user wants to skip), that's fine — just handle the GitHub response appropriately.
- Respect the user's `git add` preferences — never use `git add -A` or `git add .`.
