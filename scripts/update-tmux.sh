#!/usr/bin/env bash
# Writes per-pane status to /tmp/claude-status-$TMUX_PANE (label only).
# claude-status-active.sh reads the active pane's file for status-right.
#
# Per-window tmux options (cleared by after-select-window hook):
#   @claude_state  busy | done
#   @claude_type   ✎ | ⌕ | ◎   (code / research / explanation)
#
# Per-pane temp files:
#   /tmp/claude-tools-$PANE    tool names for current turn (cleared on UserPromptSubmit/Stop)
#   /tmp/claude-ctx-hist-$PANE last 8 context % readings (sparkline source)
#
# Safe to call with no tmux (no-op).

set -u

CONTEXT_WINDOW="${CLAUDE_TMUX_CTX_WINDOW:-1000000}"
TARGET_PANE="${TMUX_PANE:-}"

[ -z "${TMUX:-}" ] && exit 0
[ -z "$TARGET_PANE" ] && exit 0

FILE="/tmp/claude-status-${TARGET_PANE}"
TOOLS_FILE="/tmp/claude-tools-${TARGET_PANE}"
HIST_FILE="/tmp/claude-ctx-hist-${TARGET_PANE}"

payload=$(cat)
event=$(echo "$payload" | jq -r '.hook_event_name // "unknown"')
transcript=$(echo "$payload" | jq -r '.transcript_path // ""')

# Context %: integer for sparkline history, formatted for display
pct_int=""
pct=""
sparkline_str=""
if [ -n "$transcript" ] && [ -f "$transcript" ]; then
  # Filter to the main thread's most recent assistant turn:
  #  - isSidechain != true  excludes sub-agent (@-agent) requests, which carry
  #    their own small fresh context and would otherwise be grabbed as the last line
  #  - role == "assistant"  is where the API-reported context usage lives
  #  - output_tokens is excluded: context is the input side (prompt) only
  tokens=$(tac "$transcript" 2>/dev/null \
    | jq -r 'select(.message.usage and (.isSidechain != true) and (.message.role == "assistant"))
             | .message.usage
             | (.input_tokens + .cache_creation_input_tokens + .cache_read_input_tokens)' \
    | head -n 1)
  if [ -n "$tokens" ] && [ "$tokens" -gt 0 ] 2>/dev/null; then
    pct_int=$(awk -v t="$tokens" -v w="$CONTEXT_WINDOW" 'BEGIN{printf "%d", (t*100)/w}')
    pct="${pct_int}% used"

    # Update sparkline history (keep last 8 readings)
    echo "$pct_int" >> "$HIST_FILE"
    tail -n 8 "$HIST_FILE" > "${HIST_FILE}.tmp" && mv "${HIST_FILE}.tmp" "$HIST_FILE"

    # Render sparkline
    blocks=(▁ ▂ ▃ ▄ ▅ ▆ ▇ █)
    while IFS= read -r val; do
      [ -z "$val" ] && continue
      idx=$(( val * 8 / 101 ))
      [ "$idx" -gt 7 ] && idx=7
      sparkline_str="${sparkline_str}${blocks[$idx]}"
    done < "$HIST_FILE"
  fi
fi

# cut -c is byte-oriented in a UTF-8 locale and can slice mid-codepoint,
# emitting invalid bytes that corrupt the tmux status line and copy-mode.
# awk substr counts characters (respects LC_CTYPE), so it never splits a glyph.
sanitize() { tr -d '\n\r' | awk '{print substr($0,1,35)}'; }

case "$event" in
  UserPromptSubmit)
    msg=$(echo "$payload" | jq -r '.prompt // ""' | sanitize)
    label="▶ ${msg}"
    rm -f "$TOOLS_FILE"
    ;;
  PostToolUse)
    tool=$(echo "$payload" | jq -r '.tool_name // "?"')
    target=$(echo "$payload" | jq -r '
      .tool_input.file_path //
      .tool_input.command //
      .tool_input.pattern //
      .tool_input.url //
      .tool_input.description //
      ""' | sanitize)
    if [ -n "$target" ]; then
      label="${tool}: ${target}"
    else
      label="${tool}"
    fi
    echo "$tool" >> "$TOOLS_FILE"

    # Progress notification: task checked off in background window
    if [ "$tool" = "TaskUpdate" ]; then
      completed=$(echo "$payload" | jq -r '.tool_input.status // ""')
      if [ "$completed" = "completed" ]; then
        task_subject=$(echo "$payload" | jq -r '
          .tool_response |
          if type == "string" then split("\n")[0]
          elif type == "object" then (.subject // .title // "")
          else "" end' 2>/dev/null | tr -d '\000-\037' | awk '{print substr($0,1,60)}')
        task_id=$(echo "$payload" | jq -r '.tool_input.taskId // "?"')
        [ -z "$task_subject" ] && task_subject="task ${task_id} done"
        pane_window_tmp=$(tmux display-message -t "$TARGET_PANE" -p "#{window_id}" 2>/dev/null)
        active_window_tmp=$(tmux display-message -p "#{window_id}" 2>/dev/null)
        if [ -n "$pane_window_tmp" ] && [ "$pane_window_tmp" != "$active_window_tmp" ]; then
          win_name_tmp=$(tmux display-message -t "$TARGET_PANE" -p "#{window_name}" 2>/dev/null)
          pane_tty_tmp=$(tmux display-message -t "$TARGET_PANE" -p "#{pane_tty}" 2>/dev/null)
          if [ -n "$pane_tty_tmp" ] && [ -c "$pane_tty_tmp" ]; then
            printf '\033Ptmux;\033\033]9;✓ %s: %s\007\033\\' \
              "${win_name_tmp:-?}" "$task_subject" > "$pane_tty_tmp" 2>/dev/null || true
          fi
        fi
      fi
    fi
    ;;
  Stop)
    label="idle"
    ;;
  SessionStart)
    src=$(echo "$payload" | jq -r '.source // "start"')
    label="${src}"
    ;;
  *)
    label="${event}"
    ;;
esac

if [ -n "$sparkline_str" ] && [ -n "$pct" ]; then
  label="${label} [${sparkline_str} ${pct}]"
elif [ -n "$pct" ]; then
  label="${label} [${pct}]"
fi

printf '%s\n' "$label" > "$FILE"

pane_window=$(tmux display-message -t "$TARGET_PANE" -p "#{window_id}" 2>/dev/null)
active_window=$(tmux display-message -p "#{window_id}" 2>/dev/null)
is_background=0
[ -n "$pane_window" ] && [ "$pane_window" != "$active_window" ] && is_background=1

# Notification + response type on Stop
if [ "$event" = "Stop" ]; then
  # Classify from accumulated tool calls this turn
  type_sym="◎"
  if [ -f "$TOOLS_FILE" ]; then
    if grep -qE "^(Edit|Write|Bash|NotebookEdit)$" "$TOOLS_FILE" 2>/dev/null; then
      type_sym="✎"
    elif grep -qE "^(WebSearch|WebFetch)$" "$TOOLS_FILE" 2>/dev/null; then
      type_sym="⌕"
    fi
    rm -f "$TOOLS_FILE"
  fi

  win_name=$(tmux display-message -t "$TARGET_PANE" -p "#{window_name}" 2>/dev/null)
  pane_tty=$(tmux display-message -t "$TARGET_PANE" -p "#{pane_tty}" 2>/dev/null)

  if [ -n "$pane_tty" ] && [ -c "$pane_tty" ]; then
    preview=""
    if [ -n "$transcript" ] && [ -f "$transcript" ]; then
      preview=$(tac "$transcript" 2>/dev/null \
        | jq -r 'select(.message.role == "assistant") |
                  .message.content |
                  if type == "array" then (map(select(.type == "text") | .text) | first) // ""
                  else (. // "") end' 2>/dev/null \
        | head -n 1 \
        | tr -d '\000-\037' \
        | awk '{print substr($0,1,80)}')
    fi
    if [ -n "$preview" ]; then
      notif="${type_sym} ${win_name:-?}: ${preview}"
    else
      notif="${type_sym} ${win_name:-?}: response ready"
    fi
    printf '\033Ptmux;\033\033]9;%s\007\033\\' "$notif" > "$pane_tty" 2>/dev/null || true
  fi

  if [ "$is_background" = "1" ]; then
    tmux set-option -w -t "$pane_window" "@claude_state" "done" 2>/dev/null || true
    tmux set-option -w -t "$pane_window" "@claude_type" "$type_sym" 2>/dev/null || true
  fi
fi

# @claude_state for non-Stop background events
if [ "$is_background" = "1" ] && [ "$event" != "Stop" ]; then
  case "$event" in
    UserPromptSubmit|PostToolUse|SessionStart)
      current=$(tmux show-option -wqv -t "$pane_window" "@claude_state" 2>/dev/null || true)
      if [ "$current" != "done" ]; then
        tmux set-option -w -t "$pane_window" "@claude_state" "busy" 2>/dev/null || true
      fi
      ;;
  esac
fi

exit 0
