---
name: who-needs-me-for-pr
description: Show outstanding PR review requests sorted by last ping, with stall context
user-invocable: true
argument-hint: "[since:<period>] [--all]"
allowed-tools: ["Bash"]
---

# Who Needs Me for PR Review?

Find all open PRs where I am a requested reviewer OR that I previously reviewed (catches "forgot to re-request"), sorted by most recent ping. For each PR, surface context about whether I already reviewed, whether the author addressed feedback (new commits since my review), or whether the PR stalled.

**Arguments:** $ARGUMENTS

## 1. Parse arguments

The `since:` parameter accepts flexible date/time periods. Default: 2 weeks ago. `--all` overrides to no cutoff.

Extract from `$ARGUMENTS`:

| Input | Resolves To |
|-------|-------------|
| *(empty)* | 2 weeks ago from today |
| `since:2025` | `2025-01-01` |
| `since:last-week` | 7 days ago from today |
| `since:last-month` | 30 days ago from today |
| `since:2w` | 2 weeks ago |
| `since:3m` | 3 months ago |
| `since:2026-01-15` | Exact date |
| `--all` | No cutoff |

Resolve the `since:` value to an ISO date string (`YYYY-MM-DD`) using `date -d`:

```bash
# Examples of resolution:
# since:last-week  → date -d "7 days ago" +%Y-%m-%d
# since:last-month → date -d "30 days ago" +%Y-%m-%d
# since:2w         → date -d "14 days ago" +%Y-%m-%d
# since:3m         → date -d "3 months ago" +%Y-%m-%d
# since:2025       → 2025-01-01
# since:2026-01-15 → 2026-01-15
```

Pattern matching rules for the value after `since:`:
- `last-week` → 7 days ago
- `last-month` → 30 days ago
- `Nw` (e.g., `2w`, `4w`) → N*7 days ago
- `Nm` (e.g., `3m`, `6m`) → N months ago
- `Nd` (e.g., `10d`) → N days ago
- `YYYY` (4 digits) → January 1 of that year
- `YYYY-MM-DD` → exact date

## 2. Run the data-gathering script

The companion script `gather-review-context.sh` handles all API calls in parallel (8 concurrent by default) and emits jsonlines sorted by last ping descending.

```bash
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# Falls back if SKILL_DIR detection fails in a skill context:
SKILL_DIR="${SKILL_DIR:-$HOME/.claude/skills/who-needs-me-for-pr}"

bash "${SKILL_DIR}/gather-review-context.sh" "${SINCE_DATE}"
```

Pass `all` instead of a date to skip filtering.

The script outputs one JSON object per line with these fields:
`repo`, `number`, `url`, `source`, `title`, `author`, `created_at`, `updated_at`, `draft`,
`my_review_state`, `my_review_date`, `last_review_requested`, `commits_since_review`,
`author_replied_since_review`, `commit_references_review`, `last_commit_age_hours`,
`recent_comments`, `recent_review_comments`.

- `source`: `"requested"` (active review request) or `"reviewed"` (previously reviewed, no active request)
- `commits_since_review`: number of commits pushed after my last review (0 if I haven't reviewed)
- `author_replied_since_review`: true if the PR author posted any comment (issue or inline) after my last review
- `commit_references_review`: true if any post-review commit message matches patterns like "pr comment", "pr review", "address feedback", "per review", "from review"
- `last_commit_age_hours`: hours since the most recent post-review commit (0 if no commits since review)

## 6. Classify each PR

### srv-chippy = my review

`srv-chippy` is the bot account that posts findings from my `/review` skill. Treat any `recent_review_comments` entries authored by `srv-chippy` as equivalent to a personal review from me. When classifying:

- If `srv-chippy` has entries in `recent_review_comments` AND `my_review_state` is null, this is **not** a first review — srv-chippy already covered it.
- Downgrade "First review needed" → **Waiting on author** unless there are author readiness signals (re-requested, replied, commit references review).
- A PR with srv-chippy findings + readiness signals → **Re-review** territory (same as if I had reviewed it personally).

### Categories

Assign each PR to one of three categories. The key question is: "Does this require my action?"

| Category | Condition |
|----------|-----------|
| **Needs my review** | Ball is with me. Any of: (a) no review from me or srv-chippy yet, PR is not draft/blocked; (b) `source == "requested"` (active review request); (c) I (or srv-chippy) previously reviewed AND `commits_since_review > 0` AND author signaled readiness (see below). Sorted by last ping descending. |
| **Waiting on author** | I (or srv-chippy) left feedback and any of: (a) `commits_since_review == 0`; (b) `commits_since_review > 0` but no readiness signal |
| **Blocked externally** | PR is draft, OR waiting on a third party, infra dependency, or other external blocker |

### Readiness signals (priority order)

When `commits_since_review > 0`, use these signals to determine if the PR is ready for re-review:

1. **Re-requested review** (`source == "requested"`): author explicitly asked for re-review. Strongest signal; always classifies as **Needs my review**.
2. **Author replied** (`author_replied_since_review == true`): author posted a comment responding to review feedback. Strong signal.
3. **Commit references review** (`commit_references_review == true`): a commit message contains patterns like "pr comment", "pr review", "address feedback", "per review", "from review". Strong signal.
4. **24-hour cooldown** (`last_commit_age_hours >= 24`): if none of the above are met, but the last commit is 24+ hours old, the author has likely finished iterating. Weak signal; classify as "Needs my review" but note the ambiguity in the context line.

If none of these signals are met, classify as **Waiting on author** (still iterating).

Commits alone are not a signal of readiness.

### Re-review context

For PRs where I previously reviewed and the author addressed feedback (re-review scenario), summarize what changed since my last review. Use the `recent_comments` and `recent_review_comments` fields to identify what the author did:
- What feedback they addressed (e.g., "switched to module-level logger per your feedback")
- What's still open or newly discussed
- Any new questions from the author

This gives initial context so I can decide priority without opening each PR. Convey the first-review vs re-review distinction in the per-PR context line, not as a separate category.

### Re-requested but items still unaddressed

When `source == "requested"` (author explicitly re-requested review), the author believes the PR is ready. If a re-review agent finds that previously flagged items are still unaddressed (no code change fixing it AND no comment disputing it), reiterate the unaddressed items in a brief follow-up comment. The author may have missed them. Don't re-explain the full rationale; just list what's still open with a reference to the original comment.

## 7. Present results

All PR references MUST be clickable markdown links: `[repo#N](${GHE_BASE}/${REPO}/pull/${PR_NUM})`. Never output a bare `repo#N`.

### Layout

**Lead with a one-line summary**, then group by action category in this order:

1. **Needs my review** — split into "First review" and "Re-review" subsections
2. **Waiting on author** — ball is with them
3. **Blocked externally** — parked (omit section if empty)

End with a **numbered summary list** (not a dense table).

### Per-PR format

Two lines max. The link line carries the title; the context line has a status emoji, then author, then context. Use `·` to separate author from context.

```
N. [repo#N](url) — Title
   {emoji} author · context sentence with pinged date, review state, and what's needed
```

#### Status emojis

| Status | Emoji | When |
|--------|-------|------|
| First review | 🆕 | No review from me yet |
| Re-review ready | 🔄 | Author addressed feedback, ready for another look |
| Active discussion | 💬 | Ongoing conversation, author replied |
| Waiting, no activity | ⏳ | Ball is with author, no response yet |
| Stale (>1 month) | 🧊 | No activity for over 1 month |

Examples:

First review:
```
1. [simple-services#176](url) — ICR: migrate to chippy NerdClient
   🆕 duvarov · Pinged Apr 13, no review yet. nmichalesko already left feedback.
```

Re-review:
```
3. [core_python#2345](url) — YapService: make resubscription survive long publisher downtime
   🔄 mlalwani · 4 commits since your Apr 8 review. Author: "Addressed feedback, need qube test run."
```

Active discussion:
```
2. [chippy#1593](url) — Add hard_nack/soft_nack params to @app.responder
   💬 nmichalesko · Active discussion about API defaults. Author replied to your defaults suggestion.
```

Waiting on author:
```
9. [chippy#1470](url) — Add custom package registration for version logging
   ⏳ gallor · You commented Apr 14. No activity since.
```

Stale:
```
14. [queso#362](url) — Add instanceId and clientId to login response
    🧊 gallor · You commented Feb 12. No activity in 2 months.
```

### Summary list

Replace the dense table with a numbered list grouped by action. Each entry is one short line:

```markdown
## Summary: 8 need review, 5 waiting

**Needs my review**
1. [simple-services#176](url) — first review (duvarov)
2. [chippy#1593](url) — active discussion (nmichalesko)
3. [core_python#2345](url) — author addressed feedback (mlalwani)

**Waiting on author**
9. [chippy#1470](url) — no activity (gallor)
10. [queso#331](url) — no new commits since review (gallor)
```

Numbers are continuous across sections so the user can reference them (e.g., "review 3 next").

## Performance notes

- All data gathering is handled by `gather-review-context.sh` in a single invocation.
- The script parallelizes per-PR API calls (up to 8 concurrent, configurable via `MAX_PARALLEL`).
- The skill only needs two bash calls: one to resolve the date, one to run the script.
