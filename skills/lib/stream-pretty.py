#!/usr/bin/env python3
"""Pretty-print claude --output-format stream-json for GitHub Actions logs.

Adds emoji per tool type and wraps tool calls in ::group:: / ::endgroup::
so they collapse in the Actions UI, letting the final text output stand out.
"""
import json
import sys

EMOJI = {
    "Bash": "🔨",
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


def open_group():
    global in_group
    if not in_group:
        print("::group::🛠️ Tool calls", flush=True)
        in_group = True


def close_group():
    global in_group
    if in_group:
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
            print(f"{emoji} {name}", flush=True)
        elif btype == "text":
            text = block.get("text", "")
            if text.strip():
                close_group()
                print(text, end="", flush=True)

close_group()
