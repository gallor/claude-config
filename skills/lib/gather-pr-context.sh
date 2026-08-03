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
#   review-threads.json          - Review threads w/ resolution state (GraphQL)
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
# inline_full.json: all inline comments (paginated), used for dedup summary + filtering.
# inline.json: windowed subset (since last CHANGES_REQUESTED/APPROVED), passed to agents.
EXPECTED_FILES="metadata.json diff.patch inline.json inline_full.json conversation.json reviews.json review-threads.json repo.txt existing-comment-summary.json"

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

# Fetch ALL inline comments (paginated) with created_at for windowing.
# inline_full.json is the complete set; inline.json is the windowed subset
# passed to agents (see post-processing below).
gh api "repos/${REPO}/pulls/${PR}/comments" $GH_HOST_FLAG --paginate \
    --jq '[.[] | {path: .path, line: .line, body: .body, user: .user.login, created_at: .created_at}]' \
    2>/dev/null | jq -s 'add // []' \
    > "$OUTDIR/inline_full.json" &

gh api "repos/${REPO}/issues/${PR}/comments" $GH_HOST_FLAG --paginate \
    --jq '[.[] | {body: .body, user: .user.login}]' \
    2>/dev/null | jq -s 'add // []' \
    > "$OUTDIR/conversation.json" &

gh api "repos/${REPO}/pulls/${PR}/reviews" $GH_HOST_FLAG \
    --jq '[.[] | {user: .user.login, state: .state, body: .body, submitted_at: .submitted_at}]' \
    > "$OUTDIR/reviews.json" 2>/dev/null &

# Review threads with resolution state — REST comments carry no isResolved/isOutdated,
# so this GraphQL query is the only source. Feeds the APPROVE verdict gate (don't
# sign off over a live unresolved thread kaa participates in) and lets engage-open-
# threads agents skip already-resolved threads. kaa_participated = srv-chippy authored
# any comment in the thread; if the comment page truncates we assume participated
# (conservative — a missed block is worse than an over-cautious COMMENT).
#
# --paginate --slurp follows reviewThreads pageInfo across pages (a PR with >100
# threads would otherwise drop 101+ silently — the exact "missed block" the
# comment-page guard exists to prevent). --slurp wraps the pages in an outer array,
# so the jq flattens .[].data...nodes across all pages.
OWNER="${REPO%%/*}"
NAME="${REPO##*/}"
gh api graphql --paginate --slurp $GH_HOST_FLAG -f owner="$OWNER" -f repo="$NAME" -F pr="$PR" -f query='
query($owner:String!,$repo:String!,$pr:Int!,$endCursor:String){
  repository(owner:$owner,name:$repo){
    pullRequest(number:$pr){
      reviewThreads(first:100, after:$endCursor){
        pageInfo{ hasNextPage endCursor }
        nodes{
          id isResolved isOutdated
          comments(first:100){ nodes{ author{login} path line } totalCount }
        }
      }
    }
  }
}' 2>/dev/null | jq '[.[].data.repository.pullRequest.reviewThreads.nodes[] | {
      id,
      isResolved,
      isOutdated,
      kaa_participated: (
        ([.comments.nodes[].author.login] | any(. == "srv-chippy"))
        or (.comments.totalCount > (.comments.nodes | length))
      ),
      path: .comments.nodes[0].path,
      line: .comments.nodes[0].line
    }]' > "$OUTDIR/review-threads.json" 2>/dev/null &

wait

# Guarantee review-threads.json is always a valid JSON array — the GraphQL fetch
# above may have written nothing on error. Note `jq -e` on EMPTY input exits 0
# (no output is not a failure to jq), so an emptiness test alone would pass an
# empty file through; require a non-empty file that parses as an array.
if [ ! -s "$OUTDIR/review-threads.json" ] || \
   ! jq -e 'type == "array"' "$OUTDIR/review-threads.json" >/dev/null 2>&1; then
  echo '[]' > "$OUTDIR/review-threads.json"
fi

# Window inline.json to comments since the last actionable review event.
# This keeps agent context bounded on long-running PRs with many review rounds,
# while still building existing-comment-summary.json from the full set for dedup.
#
# Window anchor: the most recent CHANGES_REQUESTED or APPROVED submitted_at.
# If no such event exists, include all comments (first-review case).
#
# EXCEPTION — human comments are never windowed out. Windowing exists to bound
# kaa's own prior-round noise; a HUMAN comment is review signal the agent must
# engage (esp. premise/approach objections), and on a late review it may predate
# the anchor entirely (kaa requested after humans already reviewed). So we keep
# ALL human-authored (non-srv-chippy) comments regardless of the window, and only
# window the bot's own (srv-chippy*) comments. See flagpole#33.
WINDOW_ANCHOR=$(jq -r '
  [.[] | select(.state == "CHANGES_REQUESTED" or .state == "APPROVED")]
  | sort_by(.submitted_at) | last | .submitted_at // empty
' "$OUTDIR/reviews.json" 2>/dev/null || true)

if [[ -n "$WINDOW_ANCHOR" ]]; then
  # Keep: (a) every human (non-srv-chippy) comment, always; plus
  #       (b) bot comments created after the last CHANGES_REQUESTED/APPROVED.
  jq --arg anchor "$WINDOW_ANCHOR" \
    '[.[] | select((.user | startswith("srv-chippy") | not) or (.created_at > $anchor)) | del(.created_at)]' \
    "$OUTDIR/inline_full.json" > "$OUTDIR/inline.json" 2>/dev/null \
    || cp "$OUTDIR/inline_full.json" "$OUTDIR/inline.json"
else
  # First review: use everything (strip created_at for agent compat).
  jq '[.[] | del(.created_at)]' "$OUTDIR/inline_full.json" > "$OUTDIR/inline.json" 2>/dev/null \
    || cp "$OUTDIR/inline_full.json" "$OUTDIR/inline.json"
fi

# Generate existing-comment-summary.json from the FULL inline set (not windowed).
# Agents use this for dedup — they need to know about all prior comments, not just
# the current window, so they don't re-raise already-addressed findings.
jq '[.[] | select(.line != null) | {
  key: (.path + ":" + (.line | tostring)),
  value: (.user + ": " + (.body | gsub("\n"; " ") | .[0:80]))
}] | from_entries' "$OUTDIR/inline_full.json" > "$OUTDIR/existing-comment-summary.json" 2>/dev/null || echo '{}' > "$OUTDIR/existing-comment-summary.json"

# Generate valid-lines.json from the diff (for agent line targeting)
python3 "${HOME}/.claude/skills/lib/validate-review-comments.py" --emit-ranges "$OUTDIR/diff.patch" > "$OUTDIR/valid-lines.json" 2>/dev/null || echo '{}' > "$OUTDIR/valid-lines.json"

echo "$OUTDIR"
