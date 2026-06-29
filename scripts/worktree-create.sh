#!/usr/bin/env bash
# WorktreeCreate hook: replicates Claude Code's default git worktree creation,
# but names the branch exactly the worktree name (no "worktree-" prefix).
#
# Contract (https://code.claude.com/docs/en/hooks#worktreecreate):
#   stdin  : JSON with at least { "name": "<worktree-name>", "cwd": "<dir>" }
#   stdout : the worktree directory path (used as the session working dir)
#   stderr : diagnostics (ignored by the harness)
#
# Replicates default behavior:
#   - worktree dir: <repo-root>/.claude/worktrees/<name>
#   - baseRef=fresh: branch from origin/<default-branch>, falling back to local
#     HEAD when no remote is configured or the fetch fails
#   - existing local/remote branch of the same name is checked out instead of
#     recreated
#   - PR refs ("#1234") fetch pull/1234/head into dir pr-1234
#
# NOTE: because this hook replaces the built-in logic, .worktreeinclude is NOT
# processed and PR-URL parsing is reduced to the "#<number>" shorthand.
set -euo pipefail

input=$(cat)
name=$(printf '%s' "$input" | jq -r '.name // empty')
hook_cwd=$(printf '%s' "$input" | jq -r '.cwd // empty')

[ -n "$name" ] || { echo "worktree-create: no .name in hook input" >&2; exit 1; }

# Resolve the repo root from the hook's cwd (fall back to current dir).
cd "${hook_cwd:-$PWD}" 2>/dev/null || true
repo_root=$(git rev-parse --show-toplevel 2>/dev/null) || {
  echo "worktree-create: not inside a git repository" >&2; exit 1
}

wt_base="$repo_root/.claude/worktrees"
mkdir -p "$wt_base"

# PR shorthand: "#1234" -> fetch pull/1234/head, dir pr-1234, branch pr-1234.
if [[ "$name" =~ ^#([0-9]+)$ ]]; then
  pr_num="${BASH_REMATCH[1]}"
  branch="pr-${pr_num}"
  dir="$wt_base/$branch"
  git -C "$repo_root" fetch origin "pull/${pr_num}/head" >&2
  git -C "$repo_root" worktree add -b "$branch" "$dir" FETCH_HEAD >&2
  printf '%s\n' "$dir"
  exit 0
fi

dir="$wt_base/$name"

# Existing branch (local or remote) -> check it out rather than branching anew.
if git -C "$repo_root" show-ref --verify --quiet "refs/heads/$name"; then
  git -C "$repo_root" worktree add "$dir" "$name" >&2
  printf '%s\n' "$dir"
  exit 0
fi
if git -C "$repo_root" show-ref --verify --quiet "refs/remotes/origin/$name"; then
  git -C "$repo_root" worktree add -b "$name" "$dir" "origin/$name" >&2
  printf '%s\n' "$dir"
  exit 0
fi

# New branch. baseRef=fresh: prefer origin's default branch after a fetch;
# fall back to local HEAD when there is no usable remote.
base="HEAD"
if git -C "$repo_root" remote get-url origin >/dev/null 2>&1; then
  if git -C "$repo_root" fetch origin >&2; then
    default_ref=$(git -C "$repo_root" symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null || true)
    [ -n "$default_ref" ] && base="${default_ref#refs/remotes/}"
  fi
fi

git -C "$repo_root" worktree add -b "$name" "$dir" "$base" >&2
printf '%s\n' "$dir"
