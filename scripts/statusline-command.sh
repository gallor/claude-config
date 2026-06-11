#!/bin/bash
# Statusline command matching Powerlevel10k lean prompt style

# Read JSON input
input=$(cat)

# Extract values from JSON
cwd=$(echo "$input" | jq -r '.workspace.current_dir // .cwd')
model=$(echo "$input" | jq -r '.model.display_name')
output_style=$(echo "$input" | jq -r '.output_style.name // empty')

# Get short directory (~ for home)
short_dir="${cwd/#$HOME/~}"

# Colors
CYAN=$'\e[36m'
GREEN=$'\e[32m'
YELLOW=$'\e[33m'
BLUE=$'\e[34m'
MAGENTA=$'\e[35m'
RESET=$'\e[0m'

# Build status line components
status_parts=()

# Directory (cyan, like p10k)
status_parts+=("${CYAN}${short_dir}${RESET}")

# Git status (if in git repo)
if git -C "$cwd" rev-parse --git-dir >/dev/null 2>&1; then
    branch=$(git -C "$cwd" branch --show-current 2>/dev/null || echo "detached")
    
    # Get git status
    git_status=$(git -C "$cwd" --no-optional-locks status --porcelain 2>/dev/null)
    
    if [ -n "$git_status" ]; then
        # Has changes (yellow)
        status_parts+=("${YELLOW}${branch}${RESET}")
    else
        # Clean (green)
        status_parts+=("${GREEN}${branch}${RESET}")
    fi
fi

# Conda environment (blue)
if [ -n "$CONDA_DEFAULT_ENV" ]; then
    status_parts+=("${BLUE}${CONDA_DEFAULT_ENV}${RESET}")
fi

# Model name (magenta)
if [ -n "$model" ]; then
    status_parts+=("${MAGENTA}${model}${RESET}")
fi

# Output style (if not default)
if [ -n "$output_style" ] && [ "$output_style" != "default" ]; then
    status_parts+=("${MAGENTA}${output_style}${RESET}")
fi

# Join with spaces
printf "%s" "${status_parts[0]}"
for part in "${status_parts[@]:1}"; do
    printf " %s" "$part"
done
