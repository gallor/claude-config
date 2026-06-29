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
at_line_start = True  # track whether we need a newline before GHA commands


def ensure_newline():
    global at_line_start
    if not at_line_start:
        print(flush=True)
        at_line_start = True


def open_group(name: str):
    global in_group
    if not in_group:
        ensure_newline()
        print(f"::group::🛠️ Tool calls ({name})", flush=True)
        in_group = True


def close_group():
    global in_group
    if in_group:
        ensure_newline()
        print("::endgroup::", flush=True)
        in_group = False


while True:
    line = sys.stdin.readline()
    if not line:
        break
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
            open_group(name)
            print(f"  {emoji} {name}", flush=True)
            at_line_start = True
        elif btype == "text":
            text = block.get("text", "")
            if text.strip():
                close_group()
                print(text, end="", flush=True)
                at_line_start = text.endswith("\n")

close_group()
