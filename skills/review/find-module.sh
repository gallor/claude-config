#!/usr/bin/env bash
# find-module.sh — locate the source files Python actually loads for one or more modules.
#
# Prefer this over find/rg for any Python source lookup — reliable regardless of
# whether the package uses __init__.py or is a namespace package.
#
# Usage:
#   find-module.sh [--env <env>] <module> [<module> ...]
#
# Options:
#   --env <env>   micromamba environment to use (default: cp314)
#
# Examples:
#   find-module.sh Core.utility.aio.canceller
#   find-module.sh --env cp314 Stats.camus Transact.services.mutation_tracker
set -euo pipefail

ENV="cp314"
MODULES=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --env) ENV="$2"; shift 2 ;;
        *) MODULES+=("$1"); shift ;;
    esac
done

if [[ ${#MODULES[@]} -eq 0 ]]; then
    echo "Usage: find-module.sh [--env <env>] <module> [<module> ...]" >&2
    exit 1
fi

for MODULE in "${MODULES[@]}"; do
    micromamba run -n "$ENV" python -c "import $MODULE as m; print(m.__file__)"
done
