#!/usr/bin/env bash
# gather-review-context.sh — Collect PR review-request data for the current user.
# Called by the /who-needs-me-for-pr skill.
#
# Usage: gather-review-context.sh [SINCE_DATE]
#   SINCE_DATE  ISO date (YYYY-MM-DD) cutoff for review_requested events.
#               Omit or pass "all" to skip filtering.
#
# Output: one JSON object per PR on stdout, one per line (jsonlines),
#         sorted by last_review_requested (or updated_at) descending.
#
# Sources: Queries both --review-requested=@me (active requests) and
#          --reviewed-by=@me (previously reviewed, catches "forgot to re-request").
#          Each PR gets a "source" field: "requested" or "reviewed".
#
# Parallelism: Each PR is fetched in a background subshell (up to MAX_PARALLEL
# concurrent). Results are written to a temp directory and merged at the end.
set -euo pipefail

SINCE="${1:-all}"
MAX_PARALLEL="${MAX_PARALLEL:-8}"

ME=$(gh api user --jq '.login')
source "${HOME}/.claude/skills/lib/gh-env.sh"

TMPDIR_WORK=$(mktemp -d)
trap 'rm -rf "$TMPDIR_WORK"' EXIT

# 1. Get all open PRs requesting my review OR previously reviewed by me
declare -A SEEN
ENTRIES=()

# PRs where I'm currently requested as reviewer
while IFS= read -r line; do
  if [[ -n "$line" && -z "${SEEN[$line]:-}" ]]; then
    SEEN[$line]=requested
    ENTRIES+=("$line")
  fi
done < <(
  gh search prs --review-requested=@me --state=open --sort=created --order=asc --limit=100 \
    --json repository,number --jq '.[] | "\(.repository.nameWithOwner):\(.number)"'
)

# PRs I previously reviewed that are still open (catches "forgot to re-request")
while IFS= read -r line; do
  if [[ -n "$line" && -z "${SEEN[$line]:-}" ]]; then
    SEEN[$line]=reviewed
    ENTRIES+=("$line")
  fi
done < <(
  gh search prs --reviewed-by=@me --state=open --sort=created --order=asc --limit=100 \
    --json repository,number --jq '.[] | "\(.repository.nameWithOwner):\(.number)"'
)

if [[ ${#ENTRIES[@]} -eq 0 ]]; then
  exit 0
fi

# 2. Fetch context for a single PR (called as background job)
fetch_pr() {
  local entry="$1" outfile="$2"
  local REPO="${entry%%:*}"
  local PR_NUM="${entry##*:}"
  local SOURCE="${SEEN[$entry]:-unknown}"

  # -- PR metadata --
  local pr_json
  pr_json=$(gh api "repos/${REPO}/pulls/${PR_NUM}" \
    --jq '{title: .title, author: .user.login, created_at: .created_at, updated_at: .updated_at, draft: .draft}' 2>/dev/null) || return 0

  # -- My last review --
  local my_review
  my_review=$(gh api "repos/${REPO}/pulls/${PR_NUM}/reviews" \
    --jq "[.[] | select(.user.login==\"${ME}\")] | sort_by(.submitted_at) | last // {} | {my_review_state: .state, my_review_date: .submitted_at}" 2>/dev/null) \
    || my_review='{"my_review_state":null,"my_review_date":null}'

  # -- Last review_requested event for me --
  local last_req
  last_req=$(gh api "repos/${REPO}/issues/${PR_NUM}/timeline?per_page=100" \
    --jq "[.[] | select(.event==\"review_requested\" and .requested_reviewer.login==\"${ME}\")] | last | .created_at // empty" 2>/dev/null) \
    || last_req=""

  # Apply since filter — use last_req if available, else fall back to updated_at
  if [[ "$SINCE" != "all" ]]; then
    local filter_date="${last_req:-}"
    if [[ -z "$filter_date" ]]; then
      filter_date=$(echo "$pr_json" | jq -r '.updated_at // empty')
    fi
    if [[ -n "$filter_date" ]]; then
      local cmp_date="${filter_date%%T*}"
      if [[ "$cmp_date" < "$SINCE" ]]; then
        return 0
      fi
    fi
  fi

  # -- Commits since my last review (detect "needs re-review") --
  local commits_since_review=0
  local author_replied_since_review=false
  local commit_references_review=false
  local last_commit_age_hours=0
  local my_review_date_val
  my_review_date_val=$(echo "$my_review" | jq -r '.my_review_date // empty')
  if [[ -n "$my_review_date_val" && "$my_review_date_val" != "null" ]]; then
    # Get commits after my review, count them, and check messages + timestamps
    local commits_json
    commits_json=$(gh api "repos/${REPO}/pulls/${PR_NUM}/commits" \
      --jq "[.[] | select(.commit.committer.date > \"${my_review_date_val}\")]" 2>/dev/null) \
      || commits_json='[]'
    commits_since_review=$(echo "$commits_json" | jq 'length')

    if [[ "$commits_since_review" -gt 0 ]]; then
      # Check if any commit message references review feedback
      commit_references_review=$(echo "$commits_json" | jq '[.[].commit.message | ascii_downcase |
        test("pr comment|pr review|review feedback|address(ed|ing)? (comment|feedback|review)|per review|from review")]
        | any' 2>/dev/null) || commit_references_review=false

      # Calculate hours since last commit
      local last_commit_date
      last_commit_date=$(echo "$commits_json" | jq -r 'last.commit.committer.date // empty')
      if [[ -n "$last_commit_date" ]]; then
        local now_epoch last_epoch
        now_epoch=$(date +%s)
        last_epoch=$(date -d "$last_commit_date" +%s 2>/dev/null) || last_epoch=$now_epoch
        last_commit_age_hours=$(( (now_epoch - last_epoch) / 3600 ))
      fi
    fi

    # Check if the PR author posted any comment (issue or inline) after my review
    local pr_author
    pr_author=$(echo "$pr_json" | jq -r '.author')
    local author_issue_reply
    author_issue_reply=$(gh api "repos/${REPO}/issues/${PR_NUM}/comments?per_page=100&direction=desc" \
      --jq "[.[] | select(.user.login==\"${pr_author}\" and .created_at > \"${my_review_date_val}\")] | length" 2>/dev/null) \
      || author_issue_reply=0
    local author_review_reply
    author_review_reply=$(gh api "repos/${REPO}/pulls/${PR_NUM}/comments?per_page=100&direction=desc" \
      --jq "[.[] | select(.user.login==\"${pr_author}\" and .created_at > \"${my_review_date_val}\")] | length" 2>/dev/null) \
      || author_review_reply=0
    if [[ "$author_issue_reply" -gt 0 || "$author_review_reply" -gt 0 ]]; then
      author_replied_since_review=true
    fi
  fi

  # -- Recent issue comments (last 3) --
  local comments
  comments=$(gh api "repos/${REPO}/issues/${PR_NUM}/comments?per_page=5&direction=desc" \
    --jq '[.[-3:] | reverse[] | {author: .user.login, created_at: .created_at, body: (.body | split("\n")[0] | .[:150])}]' 2>/dev/null) \
    || comments='[]'

  # -- Recent inline review comments (last 3) --
  local review_comments
  review_comments=$(gh api "repos/${REPO}/pulls/${PR_NUM}/comments?per_page=5&direction=desc" \
    --jq '[.[-3:] | reverse[] | {author: .user.login, created_at: .created_at, body: (.body | split("\n")[0] | .[:150])}]' 2>/dev/null) \
    || review_comments='[]'

  # Assemble and write to temp file
  jq -cn \
    --arg repo "$REPO" \
    --argjson number "$PR_NUM" \
    --arg url "${GHE_BASE}/${REPO}/pull/${PR_NUM}" \
    --arg source "$SOURCE" \
    --argjson pr "$pr_json" \
    --argjson my_review "$my_review" \
    --arg last_req "${last_req:-null}" \
    --argjson commits_since_review "$commits_since_review" \
    --argjson author_replied "$author_replied_since_review" \
    --argjson commit_references_review "$commit_references_review" \
    --argjson last_commit_age_hours "$last_commit_age_hours" \
    --argjson comments "$comments" \
    --argjson review_comments "$review_comments" \
    '{
      repo: $repo,
      number: $number,
      url: $url,
      source: $source,
      title: $pr.title,
      author: $pr.author,
      created_at: $pr.created_at,
      updated_at: $pr.updated_at,
      draft: $pr.draft,
      my_review_state: $my_review.my_review_state,
      my_review_date: $my_review.my_review_date,
      last_review_requested: (if $last_req == "null" then null else $last_req end),
      commits_since_review: $commits_since_review,
      author_replied_since_review: $author_replied,
      commit_references_review: $commit_references_review,
      last_commit_age_hours: $last_commit_age_hours,
      recent_comments: $comments,
      recent_review_comments: $review_comments
    }' > "$outfile"
}

# 3. Launch parallel fetches, throttled to MAX_PARALLEL
running=0
for i in "${!ENTRIES[@]}"; do
  entry="${ENTRIES[$i]}"
  outfile="${TMPDIR_WORK}/${i}.json"

  fetch_pr "$entry" "$outfile" &
  running=$((running + 1))

  if [[ $running -ge $MAX_PARALLEL ]]; then
    wait -n 2>/dev/null || true
    running=$((running - 1))
  fi
done
wait

# 4. Merge results, sort by last_review_requested (fallback to updated_at) descending
for f in "${TMPDIR_WORK}"/*.json; do
  [[ -s "$f" ]] && cat "$f"
done | jq -s 'sort_by(.last_review_requested // .updated_at) | reverse | .[]' -c
