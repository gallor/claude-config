#!/usr/bin/env python3
"""Validate and fix review comment line numbers against a unified diff.

Usage:
    validate-review-comments.py <diff_file> <comments_json>
    validate-review-comments.py <diff_file> -  # read comments from stdin

Input comments JSON: array of objects with:
    path     (str)  - file path relative to repo root
    line     (int)  - target line number (in the new file, RIGHT side)
    body     (str)  - comment body
    start_line (int, optional) - for multi-line comments
    side     (str, optional)   - "RIGHT" (default) or "LEFT"

Output JSON (stdout):
    {
        "valid": [...],       # comments ready for the reviews API
        "rejected": [...],    # comments that can't be placed inline (with reason)
        "warnings": [...]     # comments that were auto-corrected (with details)
    }

Each valid comment has: path, line, side, body, and optionally start_line, start_side.
Each rejected comment has the original fields plus a "reason" field.
"""

import json
import re
import sys

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_diff(diff_text):
    """Parse unified diff into a map of file -> list of hunks.

    Each hunk records which line numbers are visible on each side.
    Returns: {filepath: [{"old_lines": set, "new_lines": set, "new_range": (start, end)}, ...]}
    """
    files = {}
    current_file = None
    current_hunk = None
    old_line = 0
    new_line = 0

    for raw_line in diff_text.splitlines():
        # Detect file header
        if raw_line.startswith("diff --git "):
            current_file = None
            current_hunk = None
            continue

        if raw_line.startswith("+++ b/"):
            current_file = raw_line[6:]
            if current_file not in files:
                files[current_file] = []
            continue

        if raw_line.startswith("--- "):
            continue

        if current_file is None:
            continue

        # Detect hunk header
        m = HUNK_RE.match(raw_line)
        if m:
            old_start = int(m.group(1))
            new_start = int(m.group(3))
            old_line = old_start
            new_line = new_start
            current_hunk = {"old_lines": set(), "new_lines": set()}
            files[current_file].append(current_hunk)
            continue

        if current_hunk is None:
            continue

        # Parse diff content lines
        if raw_line.startswith("+"):
            current_hunk["new_lines"].add(new_line)
            new_line += 1
        elif raw_line.startswith("-"):
            current_hunk["old_lines"].add(old_line)
            old_line += 1
        elif raw_line.startswith(" "):
            # Context line — visible on both sides
            current_hunk["old_lines"].add(old_line)
            current_hunk["new_lines"].add(new_line)
            old_line += 1
            new_line += 1
        elif raw_line.startswith("\\"):
            # "\ No newline at end of file"
            pass

    # Compute contiguous ranges for each hunk (for snapping)
    for filepath, hunks in files.items():
        for hunk in hunks:
            if hunk["new_lines"]:
                hunk["new_min"] = min(hunk["new_lines"])
                hunk["new_max"] = max(hunk["new_lines"])
            else:
                hunk["new_min"] = hunk["new_max"] = 0
            if hunk["old_lines"]:
                hunk["old_min"] = min(hunk["old_lines"])
                hunk["old_max"] = max(hunk["old_lines"])
            else:
                hunk["old_min"] = hunk["old_max"] = 0

    return files


def find_nearest_valid_line(hunks, target_line, side="RIGHT"):
    """Find the nearest valid line in any hunk for the given side.

    Returns (corrected_line, hunk_index) or (None, None) if no hunks exist.
    """
    key = "new_lines" if side == "RIGHT" else "old_lines"
    best_line = None
    best_dist = float("inf")
    best_hunk = None

    for i, hunk in enumerate(hunks):
        lines = hunk[key]
        if not lines:
            continue
        for ln in lines:
            dist = abs(ln - target_line)
            if dist < best_dist:
                best_dist = dist
                best_line = ln
                best_hunk = i

    return best_line, best_hunk


def validate_comments(diff_map, comments):
    valid = []
    rejected = []
    warnings = []

    for comment in comments:
        path = comment.get("path", "")
        line = comment.get("line")
        body = comment.get("body", "")
        start_line = comment.get("start_line")
        side = comment.get("side", "RIGHT")
        start_side = comment.get("start_side", side)

        # Normalize path — strip leading / or ./
        path = path.lstrip("./")

        if path not in diff_map:
            # Try without leading directory components that might differ
            matched = None
            for diff_path in diff_map:
                if diff_path.endswith("/" + path) or diff_path == path:
                    matched = diff_path
                    break
            if matched:
                warnings.append({
                    **comment,
                    "warning": f"Path corrected: '{comment.get('path')}' -> '{matched}'"
                })
                path = matched
            else:
                rejected.append({
                    **comment,
                    "reason": f"File '{path}' not found in diff. Available: {', '.join(sorted(diff_map.keys())[:10])}"
                })
                continue

        hunks = diff_map[path]
        line_key = "new_lines" if side == "RIGHT" else "old_lines"

        if line is None:
            rejected.append({**comment, "reason": "Missing 'line' field"})
            continue

        # Check if target line is in a hunk
        in_hunk = any(line in hunk[line_key] for hunk in hunks)

        if not in_hunk:
            # Try to snap to nearest valid line
            nearest, hunk_idx = find_nearest_valid_line(hunks, line, side)
            if nearest is not None and abs(nearest - line) <= 5:
                warnings.append({
                    **comment,
                    "warning": f"Line {line} not in diff, snapped to {nearest} (delta: {abs(nearest - line)})"
                })
                line = nearest
            elif nearest is not None:
                rejected.append({
                    **comment,
                    "reason": f"Line {line} not in any diff hunk for {path} (nearest valid: {nearest}, delta: {abs(nearest - line)})"
                })
                continue
            else:
                rejected.append({
                    **comment,
                    "reason": f"No valid lines on {side} side for {path}"
                })
                continue

        result = {"path": path, "line": line, "side": side, "body": body}

        # Handle multi-line comments
        if start_line is not None:
            # Both must be in the same hunk
            start_key = "new_lines" if start_side == "RIGHT" else "old_lines"
            same_hunk = None
            for hunk in hunks:
                if start_line in hunk[start_key] and line in hunk[line_key]:
                    same_hunk = hunk
                    break

            if same_hunk is None:
                # Try snapping start_line
                for hunk in hunks:
                    if line in hunk[line_key]:
                        # Find nearest start_line within this hunk
                        valid_starts = sorted(hunk[start_key])
                        if valid_starts:
                            candidates = [l for l in valid_starts if l <= line]
                            if candidates:
                                nearest_start = min(candidates, key=lambda l: abs(l - start_line))
                                if abs(nearest_start - start_line) <= 5:
                                    warnings.append({
                                        **comment,
                                        "warning": f"start_line {start_line} snapped to {nearest_start} (same hunk as line {line})"
                                    })
                                    start_line = nearest_start
                                    same_hunk = hunk
                        break

                if same_hunk is None:
                    # Drop multi-line, keep as single-line
                    warnings.append({
                        **comment,
                        "warning": f"start_line {comment.get('start_line')} and line {line} not in same hunk; posting as single-line comment"
                    })
                    start_line = None

            if start_line is not None and start_line != line:
                result["start_line"] = start_line
                result["start_side"] = start_side

        valid.append(result)

    return {"valid": valid, "rejected": rejected, "warnings": warnings}


def emit_ranges(diff_map):
    """Emit valid line ranges per file as JSON.

    Output format: {"file": [[start, end], ...], ...}
    Each range is a contiguous span of lines visible on the RIGHT (new) side.
    Agents use this to constrain comment targets to valid diff lines.
    """
    result = {}
    for filepath, hunks in sorted(diff_map.items()):
        ranges = []
        for hunk in hunks:
            lines = sorted(hunk["new_lines"])
            if not lines:
                continue
            # Merge into contiguous ranges
            start = lines[0]
            end = lines[0]
            for ln in lines[1:]:
                if ln == end + 1:
                    end = ln
                else:
                    ranges.append([start, end])
                    start = end = ln
            ranges.append([start, end])
        if ranges:
            result[filepath] = ranges
    return result


def main():
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        sys.exit(1)

    # --emit-ranges mode: output valid line ranges per file, no comments needed
    if sys.argv[1] == "--emit-ranges":
        if len(sys.argv) < 3:
            print("Usage: validate-review-comments.py --emit-ranges <diff_file>", file=sys.stderr)
            sys.exit(1)
        with open(sys.argv[2]) as f:
            diff_text = f.read()
        diff_map = parse_diff(diff_text)
        json.dump(emit_ranges(diff_map), sys.stdout, indent=2)
        print()
        sys.exit(0)

    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        sys.exit(1)

    diff_path = sys.argv[1]
    comments_arg = sys.argv[2]

    with open(diff_path) as f:
        diff_text = f.read()

    if comments_arg == "-":
        comments = json.load(sys.stdin)
    else:
        with open(comments_arg) as f:
            comments = json.load(f)

    diff_map = parse_diff(diff_text)
    result = validate_comments(diff_map, comments)
    json.dump(result, sys.stdout, indent=2)
    print()  # trailing newline


if __name__ == "__main__":
    main()
