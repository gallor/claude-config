---
name: create-issue
description: Create a GitHub issue for the current repository. Use this skill whenever the user wants to file, open, create, or report an issue — whether they have a detailed description already or just a rough idea. Triggers on phrases like "create an issue", "file a bug", "open an issue for this", "let's track this as an issue", or when the user describes a bug or feature request and wants it recorded.
user-invocable: true
allowed-tools: ["Bash", "Read", "Glob", "Grep"]
---

# Create Issue

Draft and create a GitHub issue for the current repository, then offer to start work on it in an isolated worktree.

**Perform ALL steps inline in the current agent. Do NOT spawn subagents.**

## Process

### Step 1 — Check for issue templates

Look for issue templates in the repository:
- `.github/ISSUE_TEMPLATE/` directory — may contain multiple `.md` or `.yml` template files
- `.github/issue_template.md` — single catch-all template

If templates exist, read them and select the most appropriate one based on the issue type (bug report, feature request, etc.). If the type is ambiguous and multiple templates are available, briefly list the options and ask the user to pick. If no templates exist, use the default format below. Follow `rules/github-issues.md` for structure, labels, and conventions.

### Step 2 — Gather issue content

Draw on everything available to draft the issue:
- What the user has already described in the conversation
- The current state of the codebase if relevant (e.g. for a bug, what the broken code looks like)
- Any error messages, stack traces, or reproduction steps mentioned

If critical information is missing (e.g. no description at all and no context), ask the user before drafting. Otherwise, make a reasonable draft and let them review it.

### Step 3 — Draft the issue

#### With a template

Fill in every section of the selected template with real content. Do not leave placeholder text or template comments in the output.

#### Default format (no template)

```
<Title in Title Case (≤72 characters)>

## Description

<What is the problem or request? What is the user-visible impact?>

## Steps to Reproduce (for bugs)

<Numbered list of steps. Include code, commands, or inputs that trigger the issue.>

## Expected Behavior

<What should happen?>

## Actual Behavior

<What happens instead? Include error messages or unexpected output verbatim.>

## Environment

<Relevant versions, OS, config — whatever is likely to matter for this issue.>
```

Omit sections that don't apply (e.g. reproduction steps for a feature request). For feature requests, replace the bug-oriented sections with a **Motivation** section explaining the use case.

**Title:** Descriptive, ≤72 characters, Title Case. For bugs, lead with the broken behavior ("Widget factory crashes when config file is missing"). For features, lead with the desired capability ("Add CSV export for querysets").

### Step 4 — Confirm with the user

Show the drafted title and body and ask for confirmation before creating the issue. This gives the user a chance to adjust wording, add detail, or pick different labels.

### Step 5 — Create the issue

**Verify labels exist before using them** — `gh label list`; an unknown label aborts `gh issue create`. Create a genuinely-needed label first (`gh label create ...`).

Once confirmed, create the issue with `gh` (source `gh-env.sh` first for GHE):

```bash
source ~/.claude/skills/lib/gh-env.sh 2>/dev/null || true
gh issue create --title "<title>" --body "<body>" [--label "<verified-label>"]
```

Capture and report the returned issue number and URL.

### Step 6 — Offer to start work

The issue is filed but no work has begun. **Do not automatically create a branch or worktree** — filing an issue for later shouldn't spawn a stray worktree. Instead, offer the handoff:

> Issue #\<number\> filed: \<url\>. Want to start work on it now? I'll check it out into a worktree via `/start-work <number>`.

If the user says yes, invoke the **`start-work` skill** with the issue number — it derives the branch, enters a worktree under `.claude/worktrees/`, and sets up the environment. If not, stop here; the issue is tracked and can be picked up later with `/start-work <number>`.
