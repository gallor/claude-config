---
name: dailylog
description: Append a brief, deduplicated summary of the work done this session to ~/code/dailylog.md, organized by day and by repo/branch. Use this skill whenever the user wants to log, record, journal, or capture what they worked on — triggers on phrases like "log this", "add to my daily log", "record what I did", "update the dailylog", "journal this work", or when wrapping up a session and the user wants a written record of the repo, branch, Jira ticket or issue, and any PR created or iterated on.
user-invocable: true
allowed-tools: ["Bash", "Read", "Agent"]
---

# Daily Log

Append a concise summary of the current session's work to `~/code/dailylog.md`. The log is organized by day (H2 date headers) and, within each day, by repo + branch (H3 headers). Summaries are bullet points. The append is **deduplication-aware**: it must not restate anything already recorded under that repo/branch section.

The reason this skill exists is to keep a low-effort running journal of engineering work. Its value depends on two things: the summary being *accurate to what actually happened*, and the file *not filling up with repeated bullets* when the skill is run several times across one piece of work. Both matter more than speed.

## Division of labor

This skill runs in two parts, because the two parts need different things:

1. **You (the current session agent) draft the summary.** You have the full context of what happened this session — that context cannot be reconstructed by a freshly-spawned subagent. Gather the repo/branch/ticket/PR facts, combine them with what you actually did, and write the bullets.
2. **A `@fast-worker` (Haiku) subagent does the append.** The file edit — read the existing log, find or create the right headers, drop already-covered bullets, write the result — is mechanical once the draft exists. Hand it off to Haiku to keep it cheap.

## Step 1 — Gather the facts (you, inline)

Collect the metadata that anchors the log entry. Run these in the repo the work happened in:

```bash
# Repo name and current branch
basename "$(git rev-parse --show-toplevel)"    # repo
git branch --show-current                       # branch

# Today's date
date +%Y-%m-%d
```

Then determine, from the session context plus git/gh:

- **Jira ticket or issue**: Look for a ticket ID in the branch name (e.g. `PROJ-1234`, `#456`), commit messages, or what the user referenced this session. If a GitHub issue was created or worked on, note its number.
- **Pull request**: Was a PR created or iterated on this session? Get its number/URL and whether it was newly created vs. updated. `gh pr view --json number,url,title,state 2>/dev/null` in the branch, if a PR exists.

If the working directory is not a git repo, ask the user which repo/branch this work belongs to rather than guessing.

## Step 2 — Draft the summary (you, inline)

Write the entry as a small set of bullets. Draw from **both** what you did this session (the actual actions, decisions, fixes) **and** git/gh state (commits, diff, PR status). The session context is what makes the log worth reading; git state is what makes it precise.

Guidelines for good bullets:

- **One fact per bullet, one sentence each.** Past tense, active voice ("Fixed the deadlock in the drain loop", not "This PR fixes...").
- **Lead with substance.** What changed and why it mattered, not process narration ("ran the tests" is only worth a bullet if the outcome mattered).
- **Fold the ticket and PR into the bullets** where natural, e.g. "Opened PR #123 addressing PROJ-456" — the header already carries repo/branch, so bullets carry the work.
- **3–6 bullets is typical.** A tiny change might be one bullet; don't pad.
- **Backtick-wrap any `<...>` placeholder or angle-bracket token** (e.g. `` `<branch>` ``, `` `<repo>/<file>` ``). A bare `<branch>` reads as an unclosed XML tag when `publish-dailylog` converts the file to Confluence storage format and silently breaks the wiki push. Wrapping it in backticks makes it valid; it also renders as code, which is what you meant anyway.

Hold this draft as a plain list of bullet strings, plus the repo, branch, and date from Step 1. You'll pass all of it to the subagent.

## Step 3 — Hand off the append to `@fast-worker`

Spawn a `@fast-worker` (Haiku) subagent with a precise brief. It owns the file mechanics and the dedup. Give it: the target file path, today's date, the repo, the branch, and your drafted bullets. Instruct it to follow the append rules below exactly.

Use the Agent tool with `subagent_type: "fast-worker"` and a prompt that contains the append contract. A template:

```
Append a daily-log entry to ~/code/dailylog.md following these rules exactly.

FACTS:
- Date: <YYYY-MM-DD>
- Repo: <repo>
- Branch: <branch>
- Candidate bullets:
  - <bullet 1>
  - <bullet 2>
  - ...

RULES: <paste the "Append contract" section below>

Report back: which bullets you appended and which you skipped as duplicates.
```

## Append contract (the rules the subagent follows)

The file uses this structure. Preserve it exactly:

```markdown
## 2026-08-03

### chippy — fix/PROJ-456-drain-deadlock
- Fixed the deadlock in the drain loop by ordering lock acquisition.
- Opened PR #123 addressing PROJ-456.

### core_python — main
- Bumped the pinned ormsgpack version to 1.5.0.

## 2026-08-04

### chippy — fix/PROJ-456-drain-deadlock
- Added a regression test reproducing the deadlock.
```

Rules, in order:

1. **If the file does not exist, create it** with the day header as the first line. (The user's setup normally has it, but never fail on a missing file.)

2. **Find or create today's day header.** Scan for an H2 matching `## <today's date>`. The "recent header" is the *last* H2 in the file. If the last H2 is today's date, reuse it. If the last H2 is an earlier date (or there are no H2s), append a new `## <today's date>` section at the end of the file, preceded by a blank line.

3. **Find or create the repo/branch header** *within today's section*. The H3 format is `### <repo> — <branch>` (note the em-dash-style separator ` — `; use a plain hyphen with spaces `- ` only if matching an existing section that used one — match whatever the existing section uses). Only look at H3s under today's H2, not previous days. If a matching H3 exists under today, append into it; otherwise add the H3 (blank line before it) at the end of today's section.

4. **Deduplicate against what's already under that repo/branch header, across ALL days, not just today.** Before writing a bullet, check whether the same information is already recorded in any existing bullet for this repo+branch (today or earlier days). "Same information" is semantic, not string-identical: "Opened PR #123" and "Created PR #123 for the deadlock fix" are the same fact — skip the new one. A bullet that adds genuinely new detail (a follow-up commit, a review addressed, a new test) is not a duplicate. When unsure, prefer skipping over duplicating; a missing near-duplicate is cheaper than a cluttered log.

5. **Backtick-wrap any bare `<...>` angle-bracket token in every surviving bullet** before writing it. A token like `<branch>`, `<repo>`, or `path/<name>` written bare breaks the downstream `publish-dailylog` sync (Confluence converts the file to XML storage format and reads `<branch>` as an unclosed tag). Wrap the whole token in single backticks (`<branch>` → `` `<branch>` ``). If the token is already inside a backticked span, leave it alone. This applies whether the bullet came from the caller or you.

6. **Append surviving bullets** under the correct H3, as `- ` list items, in the order given. Leave all other content untouched — never rewrite or reorder existing entries.

7. **Report** which bullets were appended and which were dropped as duplicates, so the caller can relay it.

## Step 4 — Relay the result

Report to the user, in one or two lines: which repo/branch section was updated, how many bullets were added, and how many were skipped as already-logged. Keep it brief; the log itself is the artifact.
