#!/usr/bin/env bash
# Prune cached PR review context for merged/closed PRs.
#
# Usage:
#   prune-pr-cache.sh              # prune all merged/closed PRs
#   prune-pr-cache.sh <repo> <pr>  # prune a specific PR
#   prune-pr-cache.sh --all        # remove entire cache
#
# Cache lives at /tmp/pr-reviews/{repo_slug}-{pr}-{sha}/

set -euo pipefail

CACHE_ROOT="/tmp/pr-reviews"

if [ ! -d "$CACHE_ROOT" ]; then
  echo "No cache directory at $CACHE_ROOT"
  exit 0
fi

source "${HOME}/.claude/skills/lib/gh-env.sh"

# --all: nuke everything
if [ "${1:-}" = "--all" ]; then
  COUNT=$(find "$CACHE_ROOT" -mindepth 1 -maxdepth 1 -type d | wc -l)
  rm -rf "${CACHE_ROOT:?}"/*
  echo "Removed $COUNT cached PR contexts"
  exit 0
fi

# Specific PR: prune-pr-cache.sh <repo> <pr>
if [ $# -eq 2 ]; then
  REPO="$1"
  PR="$2"
  REPO_SLUG=$(echo "$REPO" | tr '/' '-')
  PATTERN="${CACHE_ROOT}/${REPO_SLUG}-${PR}-*"
  COUNT=$(find $PATTERN -maxdepth 0 -type d 2>/dev/null | wc -l)
  rm -rf $PATTERN 2>/dev/null
  echo "Pruned $COUNT cached context(s) for $REPO#$PR"
  exit 0
fi

# Default: scan all cached dirs, prune merged/closed.
# A long-lived PR accumulates one cache dir per pushed commit (the sha is part
# of the key), so dedup by (repo, pr) before querying — otherwise we'd issue a
# separate `gh pr view` for every stale dir of the same PR. Query each unique
# PR once, in parallel, then prune all its dirs based on the single result.
PRUNED=0
KEPT=0
STATE_DIR=$(mktemp -d)
trap 'rm -rf "$STATE_DIR"' EXIT

# Collect unique (repo, pr) pairs across all cached dirs.
declare -A SEEN
for dir in "$CACHE_ROOT"/*/; do
  [ -d "$dir" ] || continue
  [ -f "$dir/repo.txt" ] || continue

  REPO=$(cat "$dir/repo.txt")
  BASENAME=$(basename "$dir")
  REPO_SLUG=$(echo "$REPO" | tr '/' '-')
  PR_PART="${BASENAME#${REPO_SLUG}-}"
  PR="${PR_PART%%-*}"

  [[ "$PR" =~ ^[0-9]+$ ]] || continue
  SEEN["$REPO#$PR"]=1
done

# Query each unique PR's state once, in parallel.
for key in "${!SEEN[@]}"; do
  REPO="${key%#*}"
  PR="${key#*#}"
  (
    STATE=$(gh pr view "$PR" --repo "$REPO" --json state --jq '.state' 2>/dev/null || echo "UNKNOWN")
    # Sanitize key for use as a filename.
    echo "$STATE" > "$STATE_DIR/${key//\//_}"
  ) &
done
wait

# Prune all dirs for PRs that came back MERGED/CLOSED.
for dir in "$CACHE_ROOT"/*/; do
  [ -d "$dir" ] || continue
  [ -f "$dir/repo.txt" ] || continue

  REPO=$(cat "$dir/repo.txt")
  BASENAME=$(basename "$dir")
  REPO_SLUG=$(echo "$REPO" | tr '/' '-')
  PR_PART="${BASENAME#${REPO_SLUG}-}"
  PR="${PR_PART%%-*}"
  [[ "$PR" =~ ^[0-9]+$ ]] || continue

  SANITIZED=$(echo "${REPO}#${PR}" | tr '/' '_')
  STATE=$(cat "$STATE_DIR/$SANITIZED" 2>/dev/null || echo "UNKNOWN")

  if [ "$STATE" = "MERGED" ] || [ "$STATE" = "CLOSED" ]; then
    rm -rf "$dir"
    echo "  Pruned $REPO#$PR ($STATE)"
    PRUNED=$((PRUNED + 1))
  else
    KEPT=$((KEPT + 1))
  fi
done

echo "Pruned $PRUNED, kept $KEPT cached PR contexts"
