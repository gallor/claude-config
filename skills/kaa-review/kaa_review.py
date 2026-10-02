#!/usr/bin/env python3
"""Request kaa (`srv-chippy`) as a PR reviewer, poll for its review, gather findings.

Usage:
    kaa_review.py <owner> <repo> <pr> [--budget SEC] [--resume]

Fresh run: record kaa's latest existing review id as a baseline, request
`srv-chippy` as a reviewer (which (re)triggers a kaa review — a plain push does
NOT, since submitting a review drops kaa from the requested list), then poll
until a review *newer than the baseline* appears or the per-invocation budget
elapses.

- On success: prints the gathered findings (review verdict + body + this
  review's inline comments) and clears the state file.
- On budget exhaustion: prints `KAA_PENDING …` so the caller re-invokes with
  `--resume` (which reuses the baseline and does NOT re-request).

`gh` inherits `GH_HOST` from the environment; source the repo's gh-env first for
GitHub Enterprise. Requesting the reviewer uses the REST `requested_reviewers`
endpoint (not `gh pr edit`, which is broken on our GHE).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

KAA = "srv-chippy"
DEFAULT_BUDGET_SEC = 540  # keep under the 600s Bash-tool cap; caller resumes
POLL_INTERVAL_SEC = 45


def _api(path: str, extra: list[str] | None = None):
    """Return parsed JSON from `gh api`, or None; (rc, stderr) via _api_raw for writes."""
    rc, out, _ = _api_raw(path, extra)
    if rc != 0 or not out.strip():
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def _api_raw(path: str, extra: list[str] | None = None) -> tuple[int, str, str]:
    """Run `gh api <path> [extra...]`; return (returncode, stdout, stderr)."""
    r = subprocess.run(
        ["gh", "api", path, *(extra or [])],
        capture_output=True,
        text=True,
        check=False,
    )
    return r.returncode, r.stdout, r.stderr


def kaa_reviews(owner: str, repo: str, pr: str) -> list[dict]:
    """Return all reviews on the PR authored by the kaa bot."""
    revs = _api(f"repos/{owner}/{repo}/pulls/{pr}/reviews") or []
    return [x for x in revs if (x.get("user") or {}).get("login") == KAA]


def baseline_id(owner: str, repo: str, pr: str) -> int:
    """Highest existing kaa review id (0 if none) — the 'before' mark."""
    return max((x["id"] for x in kaa_reviews(owner, repo, pr)), default=0)


def request_reviewer(owner: str, repo: str, pr: str) -> None:
    """Request srv-chippy as a reviewer (REST). A 422 (already requested) is fine."""
    _api_raw(
        f"repos/{owner}/{repo}/pulls/{pr}/requested_reviewers",
        ["-X", "POST", "-f", f"reviewers[]={KAA}"],
    )


def progress_present(owner: str, repo: str, pr: str) -> bool:
    """Whether kaa has an open `kaa-progress` 'reviewing…' comment on the PR."""
    comments = _api(f"repos/{owner}/{repo}/issues/{pr}/comments") or []
    return any(
        (c.get("user") or {}).get("login") == KAA and "kaa-progress" in (c.get("body") or "")
        for c in comments
    )


def gather(owner: str, repo: str, pr: str, review: dict) -> str:
    """Render the verdict, body, and this review's inline comments."""
    out = [
        f"KAA_REVIEW {review.get('state', '')}",
        f"PR {owner}/{repo}#{pr}",
        "",
        "=== REVIEW BODY ===",
        (review.get("body") or "").strip() or "(no body)",
    ]
    comments = _api(f"repos/{owner}/{repo}/pulls/{pr}/comments") or []
    mine = [
        c
        for c in comments
        if (c.get("user") or {}).get("login") == KAA
        and c.get("pull_request_review_id") == review["id"]
    ]
    out.append(f"\n=== INLINE COMMENTS ({len(mine)}) ===")
    for c in mine:
        loc = c.get("line") or c.get("original_line") or "?"
        out.append(f"\n--- {c.get('path', '?')}:{loc} ---")
        out.append((c.get("body") or "").strip())
    return "\n".join(out)


def _state_path(owner: str, repo: str, pr: str) -> str:
    d = os.path.expanduser("~/.cache/kaa-review")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{owner}-{repo}-{pr}.json")


def main() -> None:
    """Request (unless resuming), then poll until a new kaa review or budget end."""
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    pos = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(pos) < 3:
        print("usage: kaa_review.py <owner> <repo> <pr> [--budget SEC] [--resume]")
        raise SystemExit(2)
    owner, repo, pr = pos[0], pos[1], pos[2]
    resume = "--resume" in flags
    budget = DEFAULT_BUDGET_SEC
    for f in flags:
        if f.startswith("--budget="):
            budget = int(f.split("=", 1)[1])

    sp = _state_path(owner, repo, pr)
    if resume and os.path.exists(sp):
        base = json.load(open(sp, encoding="utf-8"))["baseline"]
    else:
        base = baseline_id(owner, repo, pr)
        request_reviewer(owner, repo, pr)
        with open(sp, "w", encoding="utf-8") as fh:
            json.dump({"baseline": base, "started_at": time.time()}, fh)

    deadline = time.time() + budget
    while True:
        new = [x for x in kaa_reviews(owner, repo, pr) if x["id"] > base]
        if new:
            print(gather(owner, repo, pr, max(new, key=lambda x: x["id"])))
            try:
                os.remove(sp)
            except OSError:
                pass
            return
        if time.time() >= deadline:
            tail = " (kaa is reviewing…)" if progress_present(owner, repo, pr) else ""
            print(f"KAA_PENDING{tail} — no new kaa review on {owner}/{repo}#{pr} yet")
            return
        time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    main()
