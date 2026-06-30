#!/usr/bin/env bash
# Shared well-known-set: chip dependency packages tracked as local source repos.
# Sourced by /release-check (dep-update checks) and /conservationist compare
# (locating changelogs for first-party deps that survive the import filter).
#
# Usage:
#   source ~/.claude/skills/lib/well-known-set.sh
#   wks_path chippy           # -> /home/$USER/git/chippy   (empty if unknown)
#   wks_changelog chippy      # -> CHANGES.md | CHANGELOG.md | "" (commits-only)
#   "${!WELL_KNOWN_SET[@]}"   # iterate package names
#
# Package name (conda/meta.yaml `name:`) -> local repo dir under ~/git.
# Note core-python's repo dir is core_python (underscore).

declare -gA WELL_KNOWN_SET=(
  [chippy]="chippy"
  [core-python]="core_python"
  [typemaster]="typemaster"
  [camus-python]="camus-python"
  [camus-ws]="camus-ws"   # no tags yet — callers skip
)

# Packages with no CHANGES file; fall back to git log between version tags.
declare -gA WKS_NO_CHANGELOG=(
  [core-python]=1
)

# Resolve a package name to its absolute local repo path ("" if unknown/missing).
wks_path() {
  local pkg="$1" sub="${WELL_KNOWN_SET[$1]:-}"
  [ -n "$sub" ] || { echo ""; return 1; }
  local p="$HOME/git/$sub"
  [ -d "$p" ] && echo "$p" || echo ""
}

# Echo the changelog filename for a package, or "" if it uses commits-only.
wks_changelog() {
  local pkg="$1" path
  [ -n "${WKS_NO_CHANGELOG[$pkg]:-}" ] && { echo ""; return 0; }
  path="$(wks_path "$pkg")"
  [ -n "$path" ] || { echo ""; return 1; }
  for f in CHANGES.md CHANGELOG.md; do
    [ -f "$path/$f" ] && { echo "$f"; return 0; }
  done
  echo ""
}

# True (0) if pkg is in the well-known set.
wks_contains() { [ -n "${WELL_KNOWN_SET[$1]:-}" ]; }
