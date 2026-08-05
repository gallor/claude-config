#!/usr/bin/env bash
# SessionStart hook: on the first session of each day, ask Claude to publish the
# daily log to Confluence. A marker file records the last date it fired so
# subsequent sessions the same day are no-ops.
set -euo pipefail

marker="$HOME/.claude/.dailylog-published-date"
today="$(date +%F)"

# Already fired today (or later): do nothing.
if [[ -f "$marker" && "$(cat "$marker" 2>/dev/null)" == "$today" ]]; then
  exit 0
fi

# Stamp the marker now so multiple sessions today don't each trigger a publish.
printf '%s' "$today" > "$marker"

jq -n --arg ctx "It's the first Claude Code session today. Invoke the /publish-dailylog skill to sync ~/code/dailylog.md to the Confluence Daily Log page. If there is nothing new to publish, say so and stop." \
  '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}'
