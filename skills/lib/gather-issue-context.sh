#!/usr/bin/env bash
# Gather issue discussion context in a single script to minimize token usage.
# Usage: gather-issue-context.sh <issue_number> [repo] [output_dir]
#
#   issue_number  Issue number (required)
#   repo          owner/repo (e.g. Chip/chippy). Omit to infer from cwd.
#   output_dir    Where to write output. Default: mktemp -d.
#
# Writes structured files to output_dir:
#   metadata.json  - Issue title, body, state, labels, assignees, comments
#   repo.txt       - owner/repo identifier
#
# Prints the output directory path to stdout.

set -euo pipefail

ISSUE="${1:?Usage: gather-issue-context.sh <issue_number> [repo] [output_dir]}"
REPO="${2:-}"
OUTDIR="${3:-$(mktemp -d /tmp/issue-review-XXXXXX)}"
mkdir -p "$OUTDIR"

# Detect GHE hostname
source "${HOME}/.claude/skills/lib/gh-env.sh"

# Repo identifier: use argument if provided, otherwise infer from cwd
if [ -z "$REPO" ]; then
  REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')
fi
echo "$REPO" > "$OUTDIR/repo.txt"

# gh issue view --json comments includes createdAt, author, body
gh issue view "$ISSUE" --repo "$REPO" \
    --json title,body,state,labels,assignees,comments \
    > "$OUTDIR/metadata.json"

echo "$OUTDIR"
