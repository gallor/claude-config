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

# Default: scan all cached dirs, prune merged/closed
PRUNED=0
KEPT=0

for dir in "$CACHE_ROOT"/*/; do
  [ -d "$dir" ] || continue
  [ -f "$dir/repo.txt" ] || continue

  REPO=$(cat "$dir/repo.txt")
  # Extract PR number from dir name: {repo_slug}-{pr}-{sha}
  BASENAME=$(basename "$dir")
  # Remove repo slug prefix and sha suffix to get PR number
  REPO_SLUG=$(echo "$REPO" | tr '/' '-')
  PR_PART="${BASENAME#${REPO_SLUG}-}"
  PR="${PR_PART%%-*}"

  if [ -z "$PR" ] || ! [[ "$PR" =~ ^[0-9]+$ ]]; then
    continue
  fi

  STATE=$(gh pr view "$PR" --repo "$REPO" --json state --jq '.state' 2>/dev/null || echo "UNKNOWN")

  if [ "$STATE" = "MERGED" ] || [ "$STATE" = "CLOSED" ]; then
    rm -rf "$dir"
    echo "  Pruned $REPO#$PR ($STATE)"
    PRUNED=$((PRUNED + 1))
  else
    KEPT=$((KEPT + 1))
  fi
done

echo "Pruned $PRUNED, kept $KEPT cached PR contexts"
