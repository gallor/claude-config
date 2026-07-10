---
name: read-pr
description: Read a pull request to collect every piece of actionable feedback left by human OR automated reviewers, and return it as a deduplicated bulleted list of discrete action items. Use whenever the user wants to know "what do I need to address on this PR", "what's the feedback on #123", "what are the reviewers asking for", "summarize the review comments", "what did CodeRabbit/the bot flag", or wants a to-do list of changes to make before a PR can merge. Also use when another skill or agent needs the set of outstanding review requests for a PR as structured input. This is feedback extraction, not code critique — for a fresh agent-based review of the diff, use /review instead.
user-invocable: true
argument-hint: "[url | owner/repo#number | number]"
allowed-tools: ["Bash", "Read", "Task"]
---

# Read a Pull Request

Collect every actionable piece of feedback on a PR — from human reviewers and automated bots alike — and return it as a single deduplicated, bulleted list of discrete action items. The output is meant to be either printed for the user or handed to another skill/agent as a work list, so it should be clean, self-contained, and free of commentary that isn't itself an action item.

**Arguments:** $ARGUMENTS

## What counts as feedback

Feedback lives in three places on a PR, and this skill gathers all of them:

- **Inline review comments** — anchored to specific file:line locations (`inline.json`).
- **Conversation comments** — general PR discussion not tied to a line (`conversation.json`).
- **Review summaries** — the top-level body a reviewer writes when submitting an APPROVE / REQUEST_CHANGES / COMMENT review, including bot reviews like CodeRabbit or a security scanner (`reviews.json`).

Both humans and bots leave feedback in all three. Treat them equally — a bot's "this can raise `KeyError`" is as actionable as a human's.

## Workflow

### 1. Resolve which PR to read

Parse `$ARGUMENTS` for a PR reference:

| Input | PR | Repo |
|-------|----|----|
| `https://.../owner/repo/pull/123` (any GitHub/GHE URL) | 123 | owner/repo |
| `owner/repo#123` | 123 | owner/repo |
| `123` or `#123` (bare number) | 123 | infer from cwd |
| *(empty)* | see below | infer from cwd |

**When no reference is given,** don't guess silently. First try to resolve the PR for the currently checked-out branch:

```bash
source ~/.claude/skills/lib/gh-env.sh && gh pr view --json number,title 2>/dev/null
```

- If that succeeds, confirm with the user: "No PR given — read #{number} ({title}) for the current branch? Or give me a URL / `owner/repo#number`." Wait for their answer.
- If it fails (no PR for this branch), ask the user to provide a URL or `owner/repo#number`, and offer **#3** as the default if they just want to proceed.

The point of prompting is that reading the wrong PR wastes the user's time and produces a confidently-wrong action list. A one-line confirmation is cheap insurance.

### 2. Gather the feedback

Use the shared context helper — it fetches all three feedback sources in parallel and caches by head SHA, so re-reads are instant:

```bash
CONTEXT_DIR=$(~/.claude/skills/lib/gather-pr-context.sh {pr} [{repo}])
```

Pass `{repo}` explicitly when you parsed it from a URL or `owner/repo#number`. Omit it only for a bare number / current-branch case (the helper infers it from cwd). **Do not run `gh repo view` yourself** — it errors on GHE; let the helper handle repo inference.

This produces under `$CONTEXT_DIR/`:

| File | Feedback source |
|------|-----------------|
| `metadata.json` | PR title, author, state (for the header) |
| `inline.json` | `[{path, line, body, user}]` — line-anchored comments |
| `conversation.json` | `[{body, user}]` — general comments |
| `reviews.json` | `[{user, state, body, submitted_at}]` — review summaries |

### 3. Extract action items (delegate to Haiku)

The extraction — reading potentially long comment threads and distilling them into discrete action items — is bounded, mechanical work that a fast model handles well and cheaply. Spawn a subagent with `model: haiku` via the Task tool, and give it `$CONTEXT_DIR` plus the extraction rules below. Have it return the finished markdown list so you can print it or pass it on.

Read `references/extraction.md` and hand its contents to the subagent as its instructions, substituting the real `$CONTEXT_DIR`. That file is the single source of truth for how to turn raw comments into a clean list — keep the rules there, not duplicated here, so the subagent and any future caller read the same spec.

**The subagent needs the PR author's login to judge resolution.** Read `author.login` from `$CONTEXT_DIR/metadata.json` (a one-field read is fine in the main session) and state it in the subagent's brief: "The PR author is `{login}`." Resolution hinges on recognizing the author's own "Fixed"/"Done" replies, and the subagent can't tell author from reviewer without being told.

The essence of the rules (full detail in `references/extraction.md`):

- **Group inline comments into threads by `file:line`, then judge each thread on its own.** The critical failure mode is treating the PR as a whole — "the author replied Fixed a few times, so it's all handled." Resolution is decided one thread at a time. An author's "Fixed" on one thread says nothing about another.
- **Silence is not resolution.** A nit or optional suggestion with no author reply is still open and still a bullet. This is the item most often dropped by mistake.
- **One comment can carry several asks.** If a single review body lists three problems, split it into three bullets — each independently checkable off.
- **Line-anchored feedback stays anchored.** Keep the `file:line` reference on the bullet so the reader knows where to act.
- **Deduplicate across sources.** The same issue often appears in an inline comment and again in a review summary, or two reviewers flag the same thing. Merge into one bullet.
- **Output only outstanding items.** This is a to-do list, not a review history — no "resolved" section. Approvals with nothing left to do produce no bullets (but say so).

### 4. Return the list

Present the result using this structure:

```markdown
# Feedback — {repo}#{pr}: {title}

_{N} action items from {M} reviewers ({list bot vs human if useful}). PR state: {open/merged/closed}._

- [ ] {action item} — _{file:line if anchored}_ ({reviewer})
- [ ] {action item} ({reviewer1}, {reviewer2})
...
```

- Lead with the count so a reader triages in one glance.
- Use checkbox bullets (`- [ ]`) — the output doubles as a to-do list.
- **Outstanding items only** — resolved threads are omitted entirely, no "already addressed" appendix. The reader wants what's left.
- If there are **no** action items (clean approval, or every thread resolved), say so plainly: "No actionable feedback — {reviewer} approved with no requested changes." Don't manufacture bullets.
- If this list is being passed to another skill/agent rather than shown to the user, the same markdown is the hand-off payload; keep it self-contained (no "see above").

**Trust the subagent's output — don't silently redo it.** The extraction is delegated on purpose; re-running it yourself in the main session defeats the cost/speed benefit. Pass its markdown through as the result. Only intervene if the output is malformed (not the expected format) or the subagent reports it couldn't read the context files.
