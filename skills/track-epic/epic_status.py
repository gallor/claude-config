#!/usr/bin/env python3
"""Scan a GitHub epic's sub-issues and render a status table.

Usage:
    epic_status.py <owner> <repo> <epic_number> [--agent N=Name ...]

Discovers sub-issues via the sub-issues API (cross-repo aware: a sub-issue may
live in another repo, and its PR is looked up there). For each sub-issue it
renders: issue number, sub-task title, rollup state, PR number, and agent.

Rollup state is derived automatically:
    todo → working → PR (draft/open) → kaa reviewing → kaa-reviewed → merged

`working` requires an `--agent` mapping (there is no programmatic issue→agent
link); the caller supplies `--agent N=Name` pairs, typically from `ListAgents`.
`gh` inherits `GH_HOST` from the environment, so source the repo's gh-env first
for GitHub Enterprise.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

KAA_LOGIN = "srv-chippy"  # GHE review bot; harmless (never matches) elsewhere
CLOSES_RE_TMPL = r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#{n}\b"


def api(path: str):
    """Return parsed JSON from `gh api <path> --paginate`, or None on failure."""
    r = subprocess.run(
        ["gh", "api", "--paginate", path],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        return None
    out = r.stdout.strip()
    if not out:
        return None
    # --paginate can concatenate multiple JSON arrays; join them.
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        merged = []
        for chunk in re.split(r"(?<=\])\s*(?=\[)", out):
            try:
                merged.extend(json.loads(chunk))
            except json.JSONDecodeError:
                pass
        return merged or None


def repo_of(issue: dict, default: tuple[str, str]) -> tuple[str, str]:
    """Return (owner, repo) for a sub-issue, falling back to the epic's repo."""
    full = (issue.get("repository") or {}).get("full_name")
    if not full:
        m = re.search(r"/repos/([^/]+)/([^/]+)$", issue.get("repository_url", ""))
        if m:
            return m.group(1), m.group(2)
    if full and "/" in full:
        owner, repo = full.split("/", 1)
        return owner, repo
    return default


def find_pr(prs: list, n: int):
    """Match a PR to sub-issue n by branch suffix, `(#n)` title, or closes-#n body."""
    closes = re.compile(CLOSES_RE_TMPL.format(n=n), re.IGNORECASE)
    for pr in prs:
        branch = pr.get("head", {}).get("ref", "")
        title = pr.get("title", "")
        body = pr.get("body") or ""
        if branch.endswith(f"-{n}") or f"(#{n})" in title or closes.search(body):
            return pr
    return None


def kaa_state(owner: str, repo: str, prnum: int):
    """Return (verdict, in_progress) for the review bot on a PR."""
    reviews = api(f"repos/{owner}/{repo}/pulls/{prnum}/reviews") or []
    kaa = [r for r in reviews if r.get("user", {}).get("login") == KAA_LOGIN]
    verdict = kaa[-1]["state"] if kaa else None
    comments = api(f"repos/{owner}/{repo}/issues/{prnum}/comments") or []
    in_progress = any(
        c.get("user", {}).get("login") == KAA_LOGIN
        and "kaa-progress" in (c.get("body") or "")
        for c in comments
    )
    return verdict, in_progress


def rollup(issue_state: str, pr, owner: str, repo: str, agent: str) -> str:
    """Derive the human-facing rollup state. PR-merge beats issue-closed."""
    if pr is None:
        if issue_state == "closed":
            return "✅ closed"
        return "🔨 working" if agent else "⬜ todo"
    if pr.get("merged_at"):
        return "✅ merged"
    verdict, in_progress = kaa_state(owner, repo, pr["number"])
    if verdict == "APPROVED":
        base = "🟢 kaa-approved"
    elif verdict == "CHANGES_REQUESTED":
        base = "🔴 kaa: changes-requested"
    elif verdict == "COMMENTED":
        base = "🔵 kaa-reviewed (commented)"
    elif in_progress:
        base = "🐍 kaa reviewing…"
    else:
        base = "📝 PR (draft)" if pr.get("draft") else "📥 PR (open)"
    return f"{base} · issue closed" if issue_state == "closed" else base


def parse_agents(argv: list[str]) -> dict[int, str]:
    """Parse repeated `--agent N=Name` args into {issue_number: name}."""
    agents: dict[int, str] = {}
    it = iter(argv)
    for tok in it:
        if tok == "--agent":
            pair = next(it, "")
            if "=" in pair:
                num, name = pair.split("=", 1)
                if num.strip().isdigit():
                    agents[int(num)] = name.strip()
    return agents


def cache_path(owner: str, repo: str, epic: str) -> str:
    """Return the per-epic signature cache path (for --quiet-if-unchanged)."""
    import os

    d = os.path.expanduser("~/.cache/track-epic")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{owner}-{repo}-{epic}.sig")


def main() -> None:
    """Fetch state and print the epic status table.

    `--quiet-if-unchanged` prints a single `NO_CHANGE` line (instead of the
    table) when the state signature matches the last run for this epic — for
    recurring monitors. Default (no flag) always prints the table.
    """
    args = [a for a in sys.argv[1:] if a != "--quiet-if-unchanged"]
    quiet = "--quiet-if-unchanged" in sys.argv
    if len(args) < 3:
        print(
            "usage: epic_status.py <owner> <repo> <epic> "
            "[--agent N=Name ...] [--quiet-if-unchanged]"
        )
        raise SystemExit(2)
    owner, repo, epic = args[0], args[1], args[2]
    agents = parse_agents(args[3:])

    epic_issue = api(f"repos/{owner}/{repo}/issues/{epic}")
    subs = api(f"repos/{owner}/{repo}/issues/{epic}/sub_issues")
    now = subprocess.run(
        ["date", "+%Y-%m-%d %H:%M"], capture_output=True, text=True, check=False
    ).stdout.strip()

    title = epic_issue["title"] if epic_issue else ""
    if not subs:
        print(f"### Epic {owner}/{repo}#{epic} — {now}")
        if title:
            print(f"_{title}_\n")
        print(
            "No sub-issues found (the epic has none, or this host lacks the "
            "sub-issues API)."
        )
        return

    # One PR fetch per distinct sub-issue repo.
    pr_cache: dict[tuple[str, str], list] = {}
    rows = []
    for sub in subs:
        n = sub["number"]
        s_owner, s_repo = repo_of(sub, (owner, repo))
        key = (s_owner, s_repo)
        if key not in pr_cache:
            pr_cache[key] = (
                api(f"repos/{s_owner}/{s_repo}/pulls?state=all&per_page=100") or []
            )
        pr = find_pr(pr_cache[key], n)
        agent = agents.get(n, "")
        state = rollup(sub["state"], pr, s_owner, s_repo, agent)
        label = f"#{n}" if (s_owner, s_repo) == (owner, repo) else f"{s_owner}/{s_repo}#{n}"
        t = sub["title"]
        t = t if len(t) <= 46 else t[:44] + "…"
        prcell = f"#{pr['number']}{' (draft)' if pr.get('draft') else ''}" if pr else "—"
        rows.append(f"| {label} | {t} | {state} | {prcell} | {agent or '—'} |")

    # Signature excludes the timestamp so unchanged state is a quiet tick.
    signature = "\n".join(rows)
    if quiet:
        path = cache_path(owner, repo, epic)
        prev = ""
        try:
            with open(path, encoding="utf-8") as fh:
                prev = fh.read()
        except OSError:
            pass
        if signature == prev:
            print(f"NO_CHANGE — {owner}/{repo}#{epic} unchanged as of {now}")
            return
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(signature)

    print(f"### Epic {owner}/{repo}#{epic} — {now}")
    if title:
        print(f"_{title}_\n")
    print("| Issue | Sub-task | State | PR | Agent |")
    print("|-------|----------|-------|----|-------|")
    print("\n".join(rows))
    print(
        "\n_States: todo → working → PR → kaa-reviewed → merged. "
        "Agent is filled from --agent mappings (name↔issue-number)._"
    )


if __name__ == "__main__":
    main()
