#!/usr/bin/env bash
# Gather all PR review context in a single script to minimize token usage.
# Usage: gather-pr-context.sh <pr_number> [repo] [output_dir]
#
#   pr_number   PR number (required)
#   repo        owner/repo (e.g. Chip/chippy). Omit to infer from cwd.
#   output_dir  Where to write output. Default: content-addressed cache dir.
#
# Writes structured files to output_dir:
#   metadata.json                - PR title, body, author, state, files, etc.
#   diff.patch                   - Full PR diff
#   inline.json                  - Existing inline review comments
#   conversation.json            - Existing conversation comments
#   reviews.json                 - Prior review summaries (body + author + state)
#   existing-comment-summary.json - {file:line: "user: summary"} for dedup
#   repo.txt                     - owner/repo identifier
#
# Caching: uses /tmp/pr-reviews/{repo_slug}-{pr}-{head_sha}/ as a
# content-addressed cache. If the directory exists with all expected files,
# prints the path and exits immediately. The head SHA makes it
# self-invalidating when new commits are pushed.
#
# Prints the output directory path to stdout.

set -euo pipefail

PR="${1:?Usage: gather-pr-context.sh <pr_number> [repo] [output_dir]}"
REPO="${2:-}"
OUTDIR="${3:-}"

# Detect GHE hostname
source "${HOME}/.claude/skills/lib/gh-env.sh"

# Repo identifier: use argument if provided, otherwise infer from cwd
if [ -z "$REPO" ]; then
  REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')
fi
REPO_FLAG="--repo $REPO"

# --- Content-addressed caching ---
CACHE_ROOT="/tmp/pr-reviews"
EXPECTED_FILES="metadata.json diff.patch inline.json conversation.json reviews.json repo.txt existing-comment-summary.json"

if [ -z "$OUTDIR" ]; then
  # Get head SHA for cache key
  HEAD_SHA=$(gh pr view "$PR" $REPO_FLAG --json headRefOid --jq '.headRefOid' 2>/dev/null || echo "")

  if [ -n "$HEAD_SHA" ]; then
    REPO_SLUG=$(echo "$REPO" | tr '/' '-')
    OUTDIR="${CACHE_ROOT}/${REPO_SLUG}-${PR}-${HEAD_SHA}"

    # Check if cache is complete
    if [ -d "$OUTDIR" ]; then
      ALL_PRESENT=true
      for f in $EXPECTED_FILES; do
        if [ ! -f "$OUTDIR/$f" ]; then
          ALL_PRESENT=false
          break
        fi
      done
      if $ALL_PRESENT; then
        echo "$OUTDIR"
        exit 0
      fi
    fi
  else
    OUTDIR=$(mktemp -d "${CACHE_ROOT}/pr-review-XXXXXX")
  fi
fi

mkdir -p "$OUTDIR"
echo "$REPO" > "$OUTDIR/repo.txt"

# Run all gh commands in parallel
gh pr view "$PR" $REPO_FLAG \
    --json title,body,author,state,baseRefName,headRefName,files,additions,deletions \
    > "$OUTDIR/metadata.json" &

gh pr diff "$PR" $REPO_FLAG \
    > "$OUTDIR/diff.patch" &

gh api "repos/${REPO}/pulls/${PR}/comments" $GH_HOST_FLAG \
    --jq '[.[] | {path: .path, line: .line, body: .body, user: .user.login}]' \
    > "$OUTDIR/inline.json" 2>/dev/null &

gh api "repos/${REPO}/issues/${PR}/comments" $GH_HOST_FLAG \
    --jq '[.[] | {body: .body, user: .user.login}]' \
    > "$OUTDIR/conversation.json" 2>/dev/null &

gh api "repos/${REPO}/pulls/${PR}/reviews" $GH_HOST_FLAG \
    --jq '[.[] | {user: .user.login, state: .state, body: .body, submitted_at: .submitted_at}]' \
    > "$OUTDIR/reviews.json" 2>/dev/null &

wait

# Generate existing-comment-summary.json from inline.json
# Maps "file:line" -> "user: first 80 chars of body" for agent dedup
jq '[.[] | select(.line != null) | {
  key: (.path + ":" + (.line | tostring)),
  value: (.user + ": " + (.body | gsub("\n"; " ") | .[0:80]) + " — " + .html_url)
}] | from_entries' "$OUTDIR/inline.json" > "$OUTDIR/existing-comment-summary.json" 2>/dev/null || echo '{}' > "$OUTDIR/existing-comment-summary.json"

# Generate valid-lines.json from the diff (for agent line targeting)
python3 "${HOME}/.claude/skills/lib/validate-review-comments.py" --emit-ranges "$OUTDIR/diff.patch" > "$OUTDIR/valid-lines.json" 2>/dev/null || echo '{}' > "$OUTDIR/valid-lines.json"

echo "$OUTDIR"
