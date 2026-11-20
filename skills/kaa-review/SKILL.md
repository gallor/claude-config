---
name: kaa-review
description: Request the kaa bot (srv-chippy) as a reviewer on a pull request, poll until its review lands, then gather and report the verdict + findings. Use whenever the user wants a kaa review kicked off and watched; triggers on "get kaa to review PR N", "request a kaa review", "poll for kaa's review", "run kaa on this PR". Also the right tool to re-trigger kaa after new commits (a push alone does not).
user-invocable: true
---

# Kaa Review

Request `srv-chippy` (the kaa review bot) on a PR, wait for the review, and report back the findings. Re-requesting is also how you get a *re-review* after pushing fixes: a plain push does not re-trigger kaa, because submitting a review drops it from the requested-reviewer list.

The work is a script (`kaa_review.py`, in this skill's directory): it baselines kaa's latest review, requests `srv-chippy`, polls for a newer review, and prints the verdict + body + that review's inline comments. Polling is slow, mechanical, and token-light, so **run it on Haiku**: the calling session just resolves the PR, delegates, and relays.

## Step 1: Resolve the PR (calling session)

From the args accept a bare number `97` (infer repo from the cwd git remote), `owner/repo#97`, or a full PR URL. Infer the repo from the remote (not `gh repo view`; `--hostname` errors on GHE):
```bash
git remote get-url origin   # git@git.drwholdings.com:Chippy/tortilla.git → Chippy / tortilla
```
If the cwd is not a git repo and no `owner/repo#N` was given, ask which repo the PR is in.

## Step 2: Delegate the request + poll + gather to Haiku (calling session)

Spawn a Haiku subagent (the **`Agent`** tool, `subagent_type: "general-purpose"`, **`model: "haiku"`**) with the brief below (filling in the resolved `<owner> <repo> <pr>`). The subagent does the GitHub writes/reads and the waiting; the calling session only relays its final output.

> **Brief for the subagent:**
> You are requesting a kaa review and watching for it. Do this:
> 1. `source ~/.claude/skills/lib/gh-env.sh 2>/dev/null || true`
> 2. Run (allow it to block; set the Bash timeout to 600000 ms):
>    `python3 ~/.claude/skills/kaa-review/kaa_review.py <owner> <repo> <pr>`
>    This requests `srv-chippy` and polls for ~9 minutes.
> 3. If its output begins with `KAA_PENDING`, kaa hasn't finished, so run it again with `--resume` appended (same 600000 ms timeout). This reuses the baseline and does **not** re-request. Repeat up to **4** times total (~36 min).
> 4. When the output begins with `KAA_REVIEW`, stop and return that full output verbatim as your final message. If still `KAA_PENDING` after 4 rounds, return that `KAA_PENDING` line so the caller knows kaa is still slow.
> Do not edit code or post anything; this only requests a review and reads the result.

## Step 3: Present (calling session)

Relay the subagent's result:
- `KAA_REVIEW <STATE>` → lead with the verdict (`🟢 APPROVE` / `🔴 REQUEST_CHANGES` / `🔵 COMMENT`), then the review body and the inline findings (grouped `file:line`), verbatim from the script. Summarize the headline in one line (e.g. "kaa requested changes: 1 critical, 2 issues"). An `APPROVE` is a code-review verdict, **not** merge-readiness; before describing the PR as mergeable or recommending a merge, run Step 4.
- `KAA_PENDING …` → tell the user kaa is still reviewing and offer to keep polling (re-invoke the skill, which resumes without re-requesting).

## Step 4: Merge-readiness check (calling session; required before any merge recommendation)

A kaa verdict is a **code-review** result, not a merge gate. A PR can be kaa-`APPROVE`d while its CI checks (unit tests, **integration tests**, lint, build) are **failing or still pending**: kaa reviews the diff, it does not run the suite (it says so itself: *"I didn't run the suite, because that is CI's job"*). So **never tell the user a PR is "ready to merge" from the review verdict alone.** Whenever you are about to describe a PR as mergeable (or the user asks whether it can merge), verify the checks and mergeability directly first:

```bash
source ~/.claude/skills/lib/gh-env.sh && export GH_HOST
gh pr checks {pr} --repo {owner}/{repo}        # per-check name + state (pass/fail/pending)
gh pr view {pr} --repo {owner}/{repo} --json mergeable,mergeStateStatus,statusCheckRollup
```

Report alongside the verdict, and gate the recommendation on it:
- **Name every check that is failing, errored, or still pending.** A failing check (e.g. a red integration-tests job) is not a nit; it blocks the merge.
- Call the PR **mergeable only** when the review is `APPROVE` **AND** every required check has passed **AND** `mergeStateStatus` is `CLEAN` (or the repo's green-equivalent).
- If any check is red or pending, say so explicitly and **do not recommend merging**: a green kaa review over a red CI run is *not* mergeable. Offer to investigate the failing check's logs, not to merge.

`gh pr checks` exits non-zero when checks are failing/pending, so treat a non-zero exit as "not mergeable", not an error to swallow. If `--json mergeStateStatus` is unavailable on the GHE version, fall back to `gh pr checks` plus the `statusCheckRollup` array for the state.

## Notes

- **Re-review after fixes:** invoking this skill again on the same PR re-requests `srv-chippy`, which re-triggers kaa on the latest commit. That is the intended way to get round 2+ (verified: a push without a re-request does nothing).
- **State:** a per-PR baseline is cached under `~/.cache/kaa-review/`; it's written on the fresh run and removed once a new review is found, so `--resume` can keep polling across invocations without re-requesting.
- **Scope:** this requests a review and reports it; it never posts comments, approves, or merges. An `APPROVE` reported here is a review verdict only; **merge-readiness is gated separately on CI checks (Step 4)**, which a kaa approval does not imply.
