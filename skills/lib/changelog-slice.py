#!/usr/bin/env python3
"""Extract changelog sections strictly between two versions.

Shared by /release-check (baseline → latest) and /conservationist compare
(from-solve → to-solve). Reads a CHANGES.md / CHANGELOG.md whose sections are
delimited by a header line containing a version (e.g. `## 2026.6.2 ...` or
`## 2026.6.2 <small>(date)</small>`). Emits sections with
  lower <  version  <= upper
in newest-first order, issue links stripped for brevity.

Usage:
    changelog-slice.py <changelog_file> --lower 2026.5.1 --upper 2026.6.2
    git -C ~/git/chippy show HEAD:CHANGES.md | changelog-slice.py - --lower X --upper Y

Exit 0 always; empty output means no sections in range.
"""
from __future__ import annotations

import argparse
import re
import sys


_VER_RE = re.compile(r"(\d+(?:\.\d+)+)")
_ISSUE_LINK_RE = re.compile(r"\s*\(\[#\d+\]\([^)]+\)\)")
_HEADER_RE = re.compile(r"^#{1,3}\s")


def _ver_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def _header_version(line: str) -> str | None:
    if not _HEADER_RE.match(line):
        return None
    m = _VER_RE.search(line)
    return m.group(1) if m else None


def slice_changelog(text: str, lower: str, upper: str) -> list[tuple[str, str]]:
    """Return [(version, section_body)] for lower < version <= upper, newest first."""
    lo, hi = _ver_tuple(lower), _ver_tuple(upper)
    lines = text.splitlines()
    sections: list[tuple[str, list[str]]] = []
    cur_ver: str | None = None
    cur_body: list[str] = []
    for line in lines:
        v = _header_version(line)
        if v is not None:
            if cur_ver is not None:
                sections.append((cur_ver, cur_body))
            cur_ver = v
            cur_body = []
        elif cur_ver is not None:
            cur_body.append(line)
    if cur_ver is not None:
        sections.append((cur_ver, cur_body))

    out = []
    for ver, body in sections:
        try:
            vt = _ver_tuple(ver)
        except ValueError:
            continue
        if lo < vt <= hi:
            cleaned = _ISSUE_LINK_RE.sub("", "\n".join(body)).strip()
            out.append((ver, cleaned))
    out.sort(key=lambda x: _ver_tuple(x[0]), reverse=True)
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("changelog", help="path to CHANGES.md, or - for stdin")
    ap.add_argument("--lower", required=True, help="exclusive lower bound version")
    ap.add_argument("--upper", required=True, help="inclusive upper bound version")
    args = ap.parse_args(argv)

    text = sys.stdin.read() if args.changelog == "-" else open(args.changelog, encoding="utf-8").read()
    for ver, body in slice_changelog(text, args.lower, args.upper):
        print(f"### {ver}\n")
        print(body + "\n" if body else "_(no entries)_\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
