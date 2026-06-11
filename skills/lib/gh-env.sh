# gh-env.sh — Shared GHE hostname detection.
# Source this file; do not execute it.
#
# Exports:
#   GH_HOST       — GHE hostname (e.g. git.drwholdings.com), or empty for github.com
#                   Also exported as env var so all gh commands use it implicitly.
#   GH_HOST_FLAG  — "--hostname <host>" or empty; for gh api calls only
#   GHE_BASE      — "https://<host>" for URL construction

# Primary: gh auth status (works outside git repos, handles SSH/HTTPS)
GH_HOST=$(gh auth status 2>&1 | grep -oP 'Logged in to \K[^ ]+' | head -1) || GH_HOST=""

# Fallback: git remote URL sniffing
if [ -z "$GH_HOST" ]; then
  _remote_url=$(git remote get-url origin 2>/dev/null) || _remote_url=""
  case "$_remote_url" in
    *git.drwholdings.com*) GH_HOST="git.drwholdings.com" ;;
  esac
  unset _remote_url
fi

# Derived variables
if [ -n "$GH_HOST" ] && [ "$GH_HOST" != "github.com" ]; then
  export GH_HOST
  GH_HOST_FLAG="--hostname $GH_HOST"
  GHE_BASE="https://$GH_HOST"
else
  GH_HOST=""
  GH_HOST_FLAG=""
  GHE_BASE="https://github.com"
fi
