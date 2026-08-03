#!/usr/bin/env bash
# find-module.sh — locate the source files Python actually loads for one or more modules.
#
# Prefer this over find/rg for any Python source lookup — reliable regardless of
# whether the package uses __init__.py or is a namespace package.
#
# Resolution strategy per module:
#   1. Import in the env and read __file__ (authoritative — resolves to the
#      installed/editable source Python actually loads).
#   2. If the import fails (module not installed, no editable install, CI
#      checkout without the package on the path), fall back to an rg-based
#      path search over the working tree. This finds the source in a fresh
#      checkout where nothing is installed editable.
#
# Usage:
#   find-module.sh [--env <env>] [--root <dir>] <module> [<module> ...]
#
# Options:
#   --env <env>    micromamba environment to use (default: cp314)
#   --root <dir>   directory to search in the rg fallback (default: cwd)
#
# Examples:
#   find-module.sh Core.utility.aio.canceller
#   find-module.sh --env cp314 Stats.camus Transact.services.mutation_tracker
set -euo pipefail

ENV="cp314"
ROOT="."
MODULES=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --env) ENV="$2"; shift 2 ;;
        --root) ROOT="$2"; shift 2 ;;
        *) MODULES+=("$1"); shift ;;
    esac
done

if [[ ${#MODULES[@]} -eq 0 ]]; then
    echo "Usage: find-module.sh [--env <env>] [--root <dir>] <module> [<module> ...]" >&2
    exit 1
fi

# rg fallback: turn a dotted module into a path fragment and look for either
# the package dir (…/foo/bar/__init__.py or namespace …/foo/bar/) or the module
# file (…/foo/bar.py). Prints all matches (a namespace package legitimately has
# several); prefixes with "# rg-fallback:" so the caller knows it wasn't the
# authoritative import resolution.
rg_fallback() {
    local module="$1"
    local rel="${module//.//}"
    local hits
    hits=$(rg --files "$ROOT" 2>/dev/null | rg -N "(^|/)${rel}(\.py|/__init__\.py|/)" || true)
    if [[ -n "$hits" ]]; then
        echo "$hits" | sed 's/^/# rg-fallback: /'
    else
        echo "# not found: $module (import failed and no file matched ${rel}.py under $ROOT)" >&2
        return 1
    fi
}

for MODULE in "${MODULES[@]}"; do
    if ! micromamba run -n "$ENV" python -c "import $MODULE as m; print(m.__file__)" 2>/dev/null; then
        rg_fallback "$MODULE" || true
    fi
done
