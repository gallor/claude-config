#!/usr/bin/env python3
"""Minimal `gh` mock for track-fix evals.

Reads canned responses from gh_responses.json (sibling file) keyed by a
normalized command signature, and logs every invocation to gh_calls.log so the
grader can verify which gh subcommands the skill actually issued.

Supported subcommands: `issue view`, `issue create`, `issue list`, `pr list`,
`label list`. Anything unrecognized exits 0 with empty output (best-effort) and
is still logged.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESPONSES = json.loads((HERE / "gh_responses.json").read_text())
LOG = HERE / "gh_calls.log"


def log(argv):
    with LOG.open("a") as f:
        f.write(" ".join(argv) + "\n")


def main():
    argv = sys.argv[1:]
    log(argv)
    if not argv:
        sys.exit(0)

    sub = " ".join(argv[:2])  # e.g. "issue view", "pr list"

    if sub == "issue view":
        resp = RESPONSES.get("issue_view")
        if resp is None or resp.get("_notfound"):
            sys.stderr.write("could not resolve to an Issue\n")
            sys.exit(1)
        print(json.dumps(resp))
        sys.exit(0)

    if sub == "pr list":
        print(json.dumps(RESPONSES.get("pr_list", [])))
        sys.exit(0)

    if sub == "issue list":
        print(json.dumps(RESPONSES.get("issue_list", [])))
        sys.exit(0)

    if sub == "label list":
        # Plain text, one label per line (matches `gh label list` default).
        for name in RESPONSES.get("labels", ["bug", "enhancement"]):
            print(f"{name}\t\t")
        sys.exit(0)

    if sub == "issue create":
        resp = RESPONSES.get("issue_create", {"url": "https://github.com/acme/repo/issues/999", "number": 999})
        # gh issue create prints the URL to stdout.
        print(resp["url"])
        sys.exit(0)

    # Unknown subcommand: succeed quietly.
    sys.exit(0)


if __name__ == "__main__":
    main()
