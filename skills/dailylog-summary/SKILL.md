---
name: dailylog-summary
description: Read the past week's entries from ~/code/dailylog.md, then append a weekly summary organized by project — one section per repo/project present in the week, each a succinct bulleted list of the tasks done — to the file, fenced by `---` dividers. EXPLICIT-INVOCATION-ONLY — run this skill ONLY when the user explicitly types the `/dailylog-summary` command. Do NOT auto-trigger it from conversational context, session wrap-up, or phrases like "summarize my week"; if the user asks for a weekly roundup in prose without invoking the command, point them at `/dailylog-summary` rather than running it. Companion to the `dailylog` skill (which logs individual sessions) and `publish-dailylog` (which mirrors the file to Confluence).
user-invocable: true
allowed-tools: ["Bash", "Read", "Edit"]
---

# Daily Log — Weekly Summary

Read the last week of entries in `~/code/dailylog.md` and append a weekly summary to the end of the file, organized **by project** — one section per repo/project that appears in the week, each holding a succinct bulleted list of the tasks done — wrapped in `---` dividers so it stands apart from the per-day entries.

> **Invocation:** This skill is **explicit-only**. Run it solely when the user types the `/dailylog-summary` command. Never fire it automatically from session wrap-up or a prose request like "summarize my week" — in that case, suggest the command instead of running it.

The value of this skill is the *consolidation*: collapsing a week of granular per-session, per-day bullets into one tidy per-project list of what got done. That is a judgment task (deciding which bullets are the same task across days, and how to phrase the rolled-up outcome), so **you (the current session agent) do it inline** rather than delegating to a subagent. There is no dedup or mechanical file-shuffling to hand off; the only file operation is a single append.

## Step 1 — Read the log and scope the week

Read the whole file:

```bash
cat_path=~/code/dailylog.md   # reference only; use the Read tool, not cat
date +%Y-%m-%d                 # today's date, to anchor the 7-day window
```

Use the **Read** tool on `~/code/dailylog.md`. If it does not exist or is empty, stop and tell the user to run the `dailylog` skill first — there is nothing to summarize.

### Guard — has a week passed since the last summary?

Before doing any synthesis, check whether a weekly summary was already generated less than 7 days ago. Scan the file for the **most recent** existing weekly-summary block; its heading carries a generated date: `## Weekly Summary (... — generated YYYY-MM-DD)`.

- If such a block exists and its `generated` date is **fewer than 7 days before today**, **stop**. Do not synthesize, do not append. Tell the user plainly that it hasn't been a week yet — name the last summary's generated date and the date the next one becomes due (generated date + 7 days).
- If the most recent summary's `generated` date is **7 or more days ago**, proceed.
- If no weekly-summary block exists yet, proceed (this is the first run).
- If an older block predates the `generated`-date format and carries no generated date, fall back to its latest range date for the 7-day comparison rather than blocking indefinitely.

The user can always override — if they explicitly ask to force/regenerate the summary anyway, skip this guard and proceed.

Identify the **day headers** (`## YYYY-MM-DD` lines) that fall in the past week:

- **Primary window:** every day header dated within the last 7 calendar days (today and the 6 preceding days).
- **Fallback:** if that window catches nothing (the log has gaps and the most recent entries are older than 7 days), take the most recent 7 distinct day-headers present in the file instead — and say so in your report, since the range won't match a literal calendar week.

Note the earliest and latest dates you actually included; you'll put that range in the summary heading.

## Step 2 — Consolidate by project (you, inline)

Read every bullet under the in-scope day headers, across all repo/branch (`###`) sections, and roll them up **per project**. This is not a copy-paste of the bullets — it is a consolidation into one succinct list per project.

1. **Group by project.** The `###` headers are `<repo> — <branch>` (e.g. `queso — sv-prefetch-506`), plus non-repo buckets that also appear (e.g. `PR Reviews`, `Discussions/Meetings`). The **project** is the repo name (the part before the ` — `), or the bucket name for non-repo sections. Merge every branch of the same repo, across all in-scope days, into one project section. So three days of `queso — sv-prefetch-506` bullets plus a `queso — main` section all collapse under a single **queso** project.
2. **Reduce each project to a succinct bulleted list of tasks done.** One bullet per distinct task/outcome. If the same task appears across multiple days (e.g. "opened PR #508" on Monday, "addressed review round 2" Tuesday, "merged" Thursday), collapse it to a single outcome bullet ("Shipped the schema_values prefetch fix — PR #508, merged"). Aim for the shortest list that still captures what was accomplished; a busy project might be 4–8 bullets, a quiet one 1–2.

Guidelines:

- **Order projects by weight.** Lead with the project that saw the most substantial work; trail with light touches (reviews, meetings).
- **Attribute to issues/PRs.** Where a bullet names an issue (`#490`) or PR (`#508`), keep the reference — it makes the summary traceable.
- **Lead each bullet with the outcome, past tense.** "Shipped…", "Fixed…", "Diagnosed…", "Designed…" — the result, not the process. Collapse "ran three review rounds / addressed Kaa round 2 / re-requested review" into one outcome like "drove PR #508 to APPROVED".
- **Keep concrete evidence that's already in the log.** If a bullet carries a measured figure (e.g. "startup 12s → 8.7s") or an issue number, keep it; don't invent numbers that aren't there.
- **Backtick-wrap any bare `<...>` angle-bracket token** (e.g. `` `<branch>` ``). A bare `<branch>` reads as an unclosed XML tag when `publish-dailylog` converts the file to Confluence storage format and silently breaks the wiki push.

## Step 3 — Append the summary, fenced by dividers

Append the summary to the **end** of the file, wrapped in `---` horizontal-rule dividers so it's visually separated from the per-day entries:

```markdown
---

## Weekly Summary (<earliest-date> to <latest-date> — generated <today's-date>)

### <project-1>
- ...
- ...

### <project-2>
- ...

### <project-3>
- ...

---
```

One `###` section per project, ordered heaviest-first, each a succinct bulleted list of tasks done.

Perform the append with the **Edit** tool, not shell redirection (the file is markdown and the CLAUDE.md conventions discourage `echo`/`cat` for writes):

- Read the file's exact final lines in Step 1.
- Use `Edit` with `old_string` = the last non-empty line(s) of the current file (verbatim, including any trailing content), and `new_string` = those same lines followed by a blank line, the opening `---`, the summary block, and the closing `---`.
- **Never rewrite or reorder existing content.** The append only adds; the per-day entries above are untouched.

If a previous weekly summary block already exists at the end of the file (a prior run of this skill), append a fresh block below it — do not overwrite the old one. Each run leaves its own dated summary. (If the user asks to *replace* the most recent summary instead of stacking, match its `## Weekly Summary (...)` heading through its closing `---` and replace that span.)

## Step 4 — Relay the result

Tell the user, in one or two lines: the date range the summary covered and which projects it grouped the week into (e.g. "grouped into queso, claude-config, typemaster, and PR reviews"). The appended summary is the artifact. If the user also wants it on the wiki, remind them the `publish-dailylog` skill mirrors the file to Confluence.
