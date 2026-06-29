#!/usr/bin/env python3
"""Pretty-print claude --output-format stream-json for GitHub Actions logs.

Adds emoji per tool type and wraps tool calls in ::group:: / ::endgroup::
so they collapse in the Actions UI, letting the final text output stand out.
"""
import json
import sys
from typing import Optional

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
last_tool: Optional[str] = None
last_tool_count = 0


def ensure_newline():
    global at_line_start
    if not at_line_start:
        print(flush=True)
        at_line_start = True


def flush_tool():
    global last_tool, last_tool_count, at_line_start
    if last_tool:
        if last_tool_count > 1:
            print(f" ×{last_tool_count}", flush=True)
            at_line_start = True
        else:
            print(flush=True)  # close the line if no dupes
            at_line_start = True
        last_tool = None
        last_tool_count = 0


def open_group(name: str):
    global in_group
    if not in_group:
        ensure_newline()
        print(f"::group::🛠️ Tool calls", flush=True)
        in_group = True


def close_group():
    global in_group
    if in_group:
        flush_tool()
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
            open_group(name)
            if name == last_tool:
                last_tool_count += 1
                print(".", end="", flush=True)
                at_line_start = False
            else:
                flush_tool()
                emoji = EMOJI.get(name, "🔧")
                print(f"  {emoji} {name}", end="", flush=True)
                at_line_start = False
                last_tool = name
                last_tool_count = 1
        elif btype == "text":
            text = block.get("text", "")
            if text.strip():
                close_group()
                print(text, end="", flush=True)
                at_line_start = text.endswith("\n")

close_group()
