#!/usr/bin/env python3
"""Pretty-print claude --output-format stream-json for GitHub Actions logs.

Adds emoji per tool type and wraps tool calls in ::group:: / ::endgroup::
so they collapse in the Actions UI, letting the final text output stand out.

Also writes the full text output to $GITHUB_STEP_SUMMARY if set, so the
review is readable in the run's Summary tab without digging into logs.
"""
import json
import os
import sys

EMOJI = {
    "Bash": "$",
    "Read": "📖",
    "Edit": "✏️",
    "Write": "✏️",
    "Agent": "🤖",
    "Task": "🤖",
    "WebSearch": "🌐",
    "WebFetch": "🌐",
    "Glob": "🔍",
    "Grep": "🔍",
    "LSP": "🔍",
    "TodoRead": "📋",
    "TodoWrite": "📋",
}

in_group = False
at_line_start = True  # track whether we need a newline before GHA commands
summary_chunks = []   # accumulate text for GITHUB_STEP_SUMMARY


def ensure_newline():
    global at_line_start
    if not at_line_start:
        print(flush=True)
        at_line_start = True


def open_group():
    global in_group
    if not in_group:
        ensure_newline()
        print("::group::🛠️ Tool calls", flush=True)
        in_group = True


def close_group():
    global in_group
    if in_group:
        ensure_newline()
        print("::endgroup::", flush=True)
        in_group = False


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        ev = json.loads(line)
    except json.JSONDecodeError:
        continue

    if ev.get("type") != "assistant":
        continue

    for block in ev.get("message", {}).get("content", []):
        btype = block.get("type")
        if btype == "tool_use":
            name = block.get("name", "unknown")
            emoji = EMOJI.get(name, "🔧")
            open_group()
            print(f"  {emoji} {name}", flush=True)
            at_line_start = True
        elif btype == "text":
            text = block.get("text", "")
            if text.strip():
                close_group()
                print(text, end="", flush=True)
                at_line_start = text.endswith("\n")
                summary_chunks.append(text)

close_group()

# Write accumulated text to GHA step summary if available
summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
if summary_path and summary_chunks:
    with open(summary_path, "a") as f:
        f.write("".join(summary_chunks))
