#!/usr/bin/env bash
# Shows Claude status for the currently active pane only.
# Called by tmux status-right via #(~/.claude/claude-status-active.sh).
# File /tmp/claude-status-$TMUX_PANE is written by update-tmux.sh
# and removed by the claude() zsh wrapper on exit.

SYMBOL="✦"
pane_id=$(tmux display-message -p '#{pane_id}' 2>/dev/null) || exit 0
file="/tmp/claude-status-${pane_id}"
[[ -f "$file" ]] || exit 0
label=$(cat "$file" 2>/dev/null)
[[ -n "$label" ]] && printf '%s %s' "$SYMBOL" "$label"
