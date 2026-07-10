# PR Feedback Extraction Rules

You are extracting actionable feedback from a pull request's review data into a single deduplicated, bulleted list of discrete action items. The list will either be shown to a developer as their to-do list before merging, or passed to another agent as a work queue. Either way it must be clean, self-contained, and contain only things someone can actually *do*.

## Inputs

You are given a context directory. Read these files from it:

- `metadata.json` — `{title, author, state, ...}`. Use for the header, and note `author.login` — you need it to judge resolution (see below).
- `inline.json` — `[{path, line, body, user}]`. Comments anchored to a specific line of the diff.
- `conversation.json` — `[{body, user}]`. General PR comments not tied to a line.
- `reviews.json` — `[{user, state, body, submitted_at}]`. The summary body a reviewer writes when submitting a review (`APPROVED`, `CHANGES_REQUESTED`, `COMMENTED`). Bots (CodeRabbit, security scanners, etc.) appear here too.

Read all four. Do not read the diff — you are extracting feedback, not reviewing code.

## First, group inline comments into threads

`inline.json` is a flat list, but comments on the **same `path:line`** form one conversation thread. Before anything else, group them by `path:line` and read each thread top to bottom. A thread typically looks like: a reviewer raises something → the author responds → maybe more back-and-forth. You are deciding, per thread, whether an action item is still *open* or already *resolved*. Do the same for `conversation.json`, grouping by topic where replies clearly chain.

This grouping is the whole game. The failure mode this skill exists to avoid is judging the PR as a whole — "the author replied 'Fixed' a few times, so everything must be handled." Resolution is decided **one thread at a time**, never for the PR at large.

## Core principle: one action item per bullet

An "action item" is a single, independently completable request. The reader should be able to do it, check it off, and move on. This is the unit you are producing.

The most common mistake is treating one *comment* as one action item. Reviewers batch multiple asks into a single comment all the time. Split them.

**Example — one comment, three asks:**

Input (a single review body):
> This is close but a few things: the `parse_config` function doesn't handle a missing `timeout` key and will `KeyError`. Also please add a test for the empty-input case. And the docstring on line 40 still says "returns a list" but it returns a dict now.

Output (three bullets):
- [ ] Handle missing `timeout` key in `parse_config` to avoid `KeyError` (alice)
- [ ] Add a test for the empty-input case (alice)
- [ ] Fix the docstring that says "returns a list" — it returns a dict now — _config.py:40_ (alice)

## Keep line-anchored feedback anchored

Feedback from `inline.json` has a `path` and `line`. Preserve that as `_{path}:{line}_` on the bullet so the reader knows exactly where to act. Conversation and review-summary feedback usually has no line; only add a location if the comment text itself names one (e.g. "the docstring on line 40").

## Deduplicate across all sources

The same issue frequently shows up more than once:

- A reviewer leaves an inline comment *and* restates it in their review summary.
- Two reviewers independently flag the same problem.
- A bot and a human both catch the same bug.

Merge these into a **single** bullet. When more than one reviewer raised it, list them — that signals importance:

- [ ] Guard against a null `user` before calling `.name` — _handlers.py:88_ (bob, coderabbit)

Judge duplication by *meaning*, not exact wording. "This can NPE" and "add a null check here" on the same line are the same item.

## Judge resolution per thread — this is the crux

For each thread, decide: is there still something the author must do? Only *open* items become bullets. But "open" is decided per thread, on evidence in that specific thread — not by the overall vibe of the PR.

**A thread is RESOLVED (drop it) only when the thread itself shows it was handled:**

- The **PR author** (`author.login` from `metadata.json`) replied that they did it: "Done", "Fixed", "Good call — changed", "removed the flag", etc. A concrete past-tense confirmation from the author is the strongest resolved signal.
- The reviewer who raised it replied that it's now fine, or withdrew it ("nvm, you're right", "ah I misread").
- It was a question, and someone answered it in a later reply in that same thread.

**A thread is OPEN (keep it as a bullet) when:**

- The reviewer raised something and **no one replied** — silence is not resolution. This is the case that gets wrongly dropped most often: a small nit or optional suggestion sitting at the end of the list with no author response is still outstanding.
- The author replied but only with uncertainty or a question, not a fix ("hmm, not sure", "should it be though?", "what do you think about X?"). The ask is still open until it's actually addressed.
- The reviewer pushed back on the author's response and the thread ends there.

The distinction to burn in: **an author saying "Fixed" on thread A tells you nothing about thread B.** Threads B, C, and D each need their own resolved-evidence. When you catch yourself concluding "the author addressed the feedback" as a blanket statement, stop — go back and check each thread has its own confirmation. A PR with four "Fixed" threads and one silent nit has exactly one action item, not zero.

**Severity is not resolution, and approval is not resolution.** These two traps are easy to fall into:

- A reviewer calling something a "non-blocking nit", "minor", or "optional" is telling you its *priority*, not that it's done. An open non-blocking nit is still an open action item — mark it `(nit)`, don't drop it.
- A reviewer *approving* the PR does not close the open threads inside their review. Reviewers routinely approve while leaving "here are a couple of small things you could tidy up" notes — those notes are open until the author actually addresses them in the thread. `APPROVED` state plus "non-blocking" wording is the exact combination that fools you into reporting zero items when there are really two or three. Approval means "I won't block merge," not "every suggestion I made is handled."

So: a merged, approved PR can absolutely still have outstanding action items — the open nits the author merged past. Report them.

Nits and optional suggestions are real action items when open — keep them and mark them `(nit)` or `(optional)` so the reader can triage. The author decides what to skip; your job is to not decide it for them by dropping the bullet.

## Also drop pure non-work

Independent of resolution, these never become bullets:

- Pure praise or acknowledgement: "LGTM", "nice", "thanks for fixing", "great catch".
- Purely informational notes with no requested change: "FYI this also runs in CI."
- A reviewer's own note that they'll handle something themselves ("I'll rebase this after merge").
- Approval boilerplate from `reviews.json` when `state` is `APPROVED` and the body requests nothing.

When in doubt on whether something is work, ask: *is there something the author must change or do?* If no, drop it.

## Handle the empty case honestly

If after all of the above there are no action items — e.g. the only review is an `APPROVED` with an empty or complimentary body — do not invent bullets. Return a single line stating that, naming the reviewer and state:

> No actionable feedback — mreviewer approved with no requested changes.

## Output format

Return exactly this markdown, nothing else (no preamble, no "here is the list"):

```markdown
# Feedback — {repo}#{pr}: {title}

_{N} action items from {M} reviewers. PR state: {state}._

- [ ] {action item} — _{path:line}_ ({reviewer})
- [ ] {action item} ({reviewer})
...
```

- **List only outstanding items.** This is a to-do list, not a review history. Resolved threads are dropped entirely — do not add a "resolved" or "already addressed" section, and do not annotate the count with how many were handled. The reader wants what's left, nothing else.
- Order bullets by severity/importance when it's discernible (blocking bugs before nits), otherwise by file then line for anchored items, with unanchored items last.
- Reviewer attribution in parentheses at the end of each bullet. Multiple reviewers: comma-separated.
- Keep each bullet to one sentence where possible. The action, then the *why* only if it isn't obvious from the action.
