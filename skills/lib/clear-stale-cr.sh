#!/usr/bin/env bash
# clear-stale-cr.sh — dismiss srv-chippy's stale meaningful review after a re-review.
#
# Handles BOTH stale directions, because a COMMENTED re-review updates GitHub's
# review decision in NEITHER — the decision uses each author's LATEST review that
# is APPROVED or CHANGES_REQUESTED (COMMENTED/DISMISSED are ignored). Call this
# AFTER submitting a re-review whose verdict is COMMENT (the only verdict that
# can leave a stale meaningful review; APPROVE/REQUEST_CHANGES set the decision
# themselves). Dismissing only the latest meaningful review is enough — an older
# one does NOT resurface.
#
#   latest-meaningful srv-chippy review is CHANGES_REQUESTED
#       -> dismiss it (unblock; the follow-up COMMENT can't clear a CR)
#   latest-meaningful srv-chippy review is APPROVED, at a commit BEHIND head_sha
#       -> dismiss it (remove a stale green check: extra code was written since
#          the approve, so it no longer certifies the current code — this is what
#          GitHub's native "dismiss stale approvals on push" does, for repos
#          without that branch-protection setting). Requires head_sha (arg 3).
#   latest-meaningful APPROVED at the SAME commit as head_sha (or no head_sha)
#       -> no-op (that would be kaa reversing its own approval of unchanged code,
#          a flip-flop we deliberately do not auto-dismiss)
#   none / all dismissed                                -> no-op
#
# The caller only invokes this on a non-CR re-review, so the latest-meaningful
# review found here is always a PRIOR review, never the fresh one.
#
# Usage:  clear-stale-cr.sh <owner/repo> <pr_number> [<head_sha>]
#   head_sha: the commit this review pass reviewed (github.event.pull_request
#   .head.sha). Omit to keep CR-only behavior (APPROVED stays a no-op).
# Requires: gh (authenticated), jq. Honors GH_HOST from env.

set -euo pipefail

REPO="${1:?usage: clear-stale-cr.sh <owner/repo> <pr> [head_sha]}"
PR="${2:?missing pr number}"
HEAD_SHA="${3:-}"
BOT="srv-chippy"

# Latest srv-chippy review whose state is APPROVED or CHANGES_REQUESTED
# (ignore COMMENTED/DISMISSED — they don't participate in the decision).
# reviews come back ascending by submitted_at; `last` gives the most recent.
# Capture commit_id too (needed to tell a stale approve from a same-SHA one).
read -r latest_state latest_id latest_commit < <(
  gh api "repos/${REPO}/pulls/${PR}/reviews" --paginate \
    --jq "[.[] | select(.user.login==\"${BOT}\" and (.state==\"APPROVED\" or .state==\"CHANGES_REQUESTED\"))] | last | \"\(.state // \"NONE\") \(.id // 0) \(.commit_id // \"\")\"" 2>/dev/null
) || { echo "no-op: could not read reviews"; exit 0; }

# Permalink to the superseding review — the latest srv-chippy COMMENT/APPROVE
# (the follow-up carrying the substance), NOT "latest overall" (could be a
# dismissed review). Shared by both dismiss paths.
dismiss() {
  local target_id="$1" kind="$2"
  local super_url
  super_url=$(gh api "repos/${REPO}/pulls/${PR}/reviews" --paginate \
    --jq "[.[] | select(.user.login==\"${BOT}\" and (.state==\"COMMENTED\" or .state==\"APPROVED\"))] | last | .html_url // empty" 2>/dev/null)
  local msg
  if [ -n "${super_url}" ]; then msg="Superseded by ${super_url}"; else msg="Superseded by follow-up review."; fi
  gh api "repos/${REPO}/pulls/${PR}/reviews/${target_id}/dismissals" \
    --method PUT -f message="${msg}" -f event=DISMISS >/dev/null
  echo "dismissed stale ${kind} review ${target_id} on ${REPO}#${PR} (msg: ${msg})."
}

case "${latest_state:-NONE}" in
  CHANGES_REQUESTED)
    dismiss "${latest_id}" "CHANGES_REQUESTED"
    ;;
  APPROVED)
    if [ -n "${HEAD_SHA}" ] && [ -n "${latest_commit}" ] && [ "${latest_commit}" != "${HEAD_SHA}" ]; then
      # Extra code written since the approve — it no longer covers current HEAD.
      dismiss "${latest_id}" "stale APPROVE (approved ${latest_commit:0:7}, head ${HEAD_SHA:0:7})"
    else
      echo "no-op: latest meaningful ${BOT} review is APPROVED at current head (or no head_sha given) — not a stale approve."
    fi
    ;;
  *)
    echo "no-op: no active ${BOT} meaningful review to clear."
    ;;
esac
