#!/usr/bin/env bash
#
# claude-migrate.sh — move Claude Code persistent state between machines.
#
# Assumes SAME username and SAME home/code layout on both machines (the
# ~/.claude symlinks and per-project keys are absolute paths).
#
# Usage:
#   claude-migrate.sh export [OUTFILE]   # run on OLD machine
#   claude-migrate.sh import [INFILE]    # run on NEW machine
#
# What travels:   config, prompt history, session transcripts + per-project
#                 memory, saved plans, agent-memory, edit history, plugins.
# What does NOT:  credentials (re-auth), runtime/daemon state, caches, and any
#                 RUNNING background agents — those are live processes; resume
#                 their sessions on the new box instead.
#
# The git-backed config (agents/commands/rules/skills/scripts/CLAUDE.md) is a
# set of symlinks into ~/code/claude-config. This script records them on export
# and recreates them on import after cloning the repo; their CONTENT comes from
# the repo, not the tarball.

set -euo pipefail

CLAUDE_DIR="$HOME/.claude"
CONFIG_JSON="$HOME/.claude.json"
CONFIG_REPO_DIR="$HOME/code/claude-config"
CONFIG_REPO_REMOTE="git@git.drwholdings.com:gallor/claude-config.git"
MANIFEST_NAME=".claude-symlinks.manifest"

# Runtime/cache/credential state that must NOT be copied. Paths are relative to
# $HOME so they match the archive member names.
EXCLUDES=(
  ".claude/.credentials.json"
  ".claude/daemon"
  ".claude/daemon.log"
  ".claude/tasks"
  ".claude/jobs"
  ".claude/teams"
  ".claude/session-env"
  ".claude/sessions"
  ".claude/shell-snapshots"
  ".claude/paste-cache"
  ".claude/statsig"
  ".claude/stats-cache.json"
  ".claude/mcp-needs-auth-cache.json"
  ".claude/.last-cleanup"
  ".claude/debug"
  ".claude/old"
)

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

do_export() {
  local outfile="${1:-$HOME/claude-migration-$(hostname -s)-$(date +%Y%m%d).tgz}"

  [[ -d "$CLAUDE_DIR" ]] || die "no ~/.claude on this machine — nothing to export"

  # Record the top-level symlinks (name -> target) so import recreates them.
  local manifest="$CLAUDE_DIR/$MANIFEST_NAME"
  find "$CLAUDE_DIR" -maxdepth 1 -type l -printf '%f\t%l\n' > "$manifest"
  log "recorded $(wc -l < "$manifest") symlink(s) to $MANIFEST_NAME"

  # Build tar args: exclude runtime/cache dirs AND the symlinks themselves
  # (their targets come from the cloned repo, not the archive).
  local tar_args=(--create --gzip --file "$outfile" -C "$HOME")
  local ex
  for ex in "${EXCLUDES[@]}"; do
    tar_args+=(--exclude="$ex")
  done
  local name
  while IFS=$'\t' read -r name _; do
    tar_args+=(--exclude=".claude/$name")
  done < "$manifest"

  # Members to archive: the .claude tree and the top-level config file.
  local members=(".claude")
  [[ -f "$CONFIG_JSON" ]] && members+=(".claude.json") || warn "no ~/.claude.json found"

  log "creating archive: $outfile"
  tar "${tar_args[@]}" "${members[@]}"

  local size
  size="$(du -h "$outfile" | cut -f1)"
  log "done — $outfile ($size)"
  echo
  echo "Next: copy it to the new machine and run:"
  echo "    $CONFIG_REPO_DIR/scripts/$(basename "$0") import $(basename "$outfile")"
  echo "(clone $CONFIG_REPO_REMOTE into ~/code/claude-config there first, or let import do it)"
}

do_import() {
  local infile="${1:-}"
  [[ -n "$infile" ]] || die "usage: $(basename "$0") import <archive.tgz>"
  [[ -f "$infile" ]] || die "archive not found: $infile"
  infile="$(cd "$(dirname "$infile")" && pwd)/$(basename "$infile")"

  # 1. Ensure the git-backed config repo exists so symlink targets resolve.
  if [[ ! -d "$CONFIG_REPO_DIR" ]]; then
    log "cloning claude-config into $CONFIG_REPO_DIR"
    mkdir -p "$(dirname "$CONFIG_REPO_DIR")"
    git clone "$CONFIG_REPO_REMOTE" "$CONFIG_REPO_DIR"
  else
    log "claude-config already present at $CONFIG_REPO_DIR"
  fi

  # 2. Guard against clobbering an existing populated ~/.claude.
  if [[ -e "$CLAUDE_DIR/projects" ]]; then
    warn "~/.claude already contains data on this machine."
    read -r -p "Overwrite/merge extracted state into it? [y/N] " ans
    [[ "$ans" == [yY] ]] || die "aborted"
  fi

  # 3. Extract data into $HOME.
  log "extracting $infile"
  mkdir -p "$CLAUDE_DIR"
  tar --extract --gzip --file "$infile" -C "$HOME"

  # 4. Recreate the top-level symlinks from the manifest.
  local manifest="$CLAUDE_DIR/$MANIFEST_NAME"
  if [[ -f "$manifest" ]]; then
    local name target
    while IFS=$'\t' read -r name target; do
      [[ -n "$name" ]] || continue
      ln -sfn "$target" "$CLAUDE_DIR/$name"
      [[ -e "$CLAUDE_DIR/$name" ]] || warn "symlink $name -> $target is dangling (clone/target missing?)"
    done < "$manifest"
    log "recreated $(grep -c . "$manifest") symlink(s)"
  else
    warn "no symlink manifest in archive — skipping symlink recreation"
  fi

  echo
  log "import complete."
  echo "Remaining manual steps:"
  echo "  1. Run 'claude' and authenticate (credentials were intentionally not copied)."
  echo "  2. Re-auth/verify MCP servers (git-rw, wiki, miro, nacho) — they need local OAuth/binaries."
  echo "  3. 'claude --resume' in a project dir to confirm transcripts + memory loaded."
  echo "  4. Any background agents that were running on the old box must be re-started here."
}

main() {
  local cmd="${1:-}"
  shift || true
  case "$cmd" in
    export) do_export "$@" ;;
    import) do_import "$@" ;;
    ""|-h|--help|help)
      sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'
      ;;
    *) die "unknown command: $cmd (use export|import)" ;;
  esac
}

main "$@"
