#!/usr/bin/env bash
# Review-gate stamp: records that a local /review ran over a specific reviewed
# diff, so /pr-pipeline can tell whether the current code was already reviewed
# before opening a PR. Correctness is carried entirely by the content hash — a
# stamp matches iff (base_ref + reviewed diff) is byte-identical to what was
# reviewed, so any tracked change (committed OR uncommitted) invalidates it
# (brand-new untracked files excepted — they're invisible to git diff). Pruning
# is pure housekeeping (a stale stamp simply never matches current HEAD).
#
# Usage:
#   review-stamp.sh key   <base_ref> [repo_root]          -> prints the stamp key (hash)
#   review-stamp.sh write <base_ref> <state> <mode> [repo_root]
#   review-stamp.sh check <base_ref> [repo_root]          -> prints stamp JSON if match, else nothing (exit 1)
#   review-stamp.sh prune                                 -> delete stamps older than TTL
#
#   state = clean | capped | halted     (how a --loop ended; report-only passes use "clean")
#   mode  = loop | report
#
# Stamp file: /tmp/review-done-<repo_slug>-<hash>, contents = one JSON line.

set -euo pipefail

STAMP_ROOT="/tmp"
STAMP_PREFIX="review-done-"
TTL_DAYS=7

cmd="${1:-}"

_repo_slug() {
  local root="$1"
  # origin URL if available, else the toplevel dir name — just needs to be stable per repo.
  local url
  url=$(git -C "$root" config --get remote.origin.url 2>/dev/null || true)
  if [ -n "$url" ]; then
    echo "$url" | sed -E 's#.*[/:]([^/]+/[^/]+?)(\.git)?$#\1#' | tr '/:' '--'
  else
    basename "$(git -C "$root" rev-parse --show-toplevel 2>/dev/null || echo "$root")"
  fi
}

# Abort (exit 3) if the base ref doesn't resolve — shallow clone, unfetched
# remote-tracking ref, base renamed/deleted upstream. This MUST be called directly
# from a subcommand arm, never from inside command substitution: `set -e` does NOT
# propagate a non-zero exit out of a `$(...)` nested inside another assignment
# (verified), so a guard buried in `_key` (reached via `$(_stamp_path → $(_key))`)
# is silently swallowed and the key degrades to a content-independent constant —
# the exact FALSE-MATCH that lets /pr-pipeline skip review on unreviewed code.
# Guarding up front on the direct path makes a bad base a gate miss (re-review),
# which is fail-safe, not false-clean.
_require_base() {
  local base="$1" root="$2"
  git -C "$root" rev-parse --verify --quiet "$base^{commit}" >/dev/null \
    || { echo "review-stamp: base ref '$base' does not resolve" >&2; exit 3; }
}

_key() {
  local base="$1" root="$2"
  # The reviewed content = base ref identity + the full diff of working tree vs base.
  # Include base so a rebase onto a new base invalidates. Tracked edits (committed or
  # not) are in the diff, so they invalidate too. (Known limitation, shared with the
  # rest of the skill family: brand-new *untracked* files are invisible to git diff.)
  # Callers must _require_base first; this assumes the base resolves.
  { printf '%s\n' "$base"; git -C "$root" diff "$base"; } | sha256sum | cut -d' ' -f1
}

_stamp_path() {
  local base="$1" root="$2"
  local slug key
  slug=$(_repo_slug "$root")
  key=$(_key "$base" "$root")
  echo "${STAMP_ROOT}/${STAMP_PREFIX}${slug}-${key}"
}

case "$cmd" in
  key)
    # Debug/introspection aid — prints the stamp key for a given base. Not called by
    # the skills (which use write/check/prune); handy for manual verification.
    base="${2:?usage: review-stamp.sh key <base_ref> [repo_root]}"; root="${3:-$(pwd)}"
    _require_base "$base" "$root"   # direct call — exit propagates (see _require_base)
    _key "$base" "$root"
    ;;

  write)
    # Arity-check before set -u dereferences $3/$4 (a model invokes this from
    # paraphrased markdown; a dropped arg should print usage, not a raw bash trace).
    [ $# -ge 4 ] || { echo "usage: review-stamp.sh write <base_ref> <state> <mode> [repo_root]" >&2; exit 2; }
    base="$2"; state="$3"; mode="$4"; root="${5:-$(pwd)}"
    _require_base "$base" "$root"   # MUST precede _stamp_path: the guard can't live inside
                                    # the nested $(_stamp_path → $(_key)) — set -e swallows it there.
    path=$(_stamp_path "$base" "$root")
    # Only state and mode have readers (the /pr-pipeline step-0 gate branches on them).
    printf '{"state":"%s","mode":"%s"}\n' "$state" "$mode" > "$path"
    echo "$path"
    ;;

  check)
    base="$2"; root="${3:-$(pwd)}"
    _require_base "$base" "$root"   # direct call, before the nested substitution below
    path=$(_stamp_path "$base" "$root")
    if [ -f "$path" ]; then
      cat "$path"
      exit 0
    fi
    exit 1
    ;;

  prune)
    find "$STAMP_ROOT" -maxdepth 1 -name "${STAMP_PREFIX}*" -mtime "+${TTL_DAYS}" -delete 2>/dev/null || true
    echo "Pruned review stamps older than ${TTL_DAYS}d"
    ;;

  *)
    echo "usage: review-stamp.sh {key|write|check|prune} ..." >&2
    exit 2
    ;;
esac
