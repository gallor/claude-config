#!/usr/bin/env python3
"""Run deterministic static analysis tools on changed Python and Rust files.

Usage: static-analysis.py <base_ref> [repo_root] [output_dir]

  base_ref    Git ref to diff against (e.g. origin/main, HEAD~1, abc123)
  repo_root   Repository root directory. Default: cwd.
  output_dir  Where to write output. Default: mktemp -d.

Writes:
  static-analysis.json  - Structured results from all tools

Prints the output directory path to stdout.
Tools that are not installed or not applicable are skipped gracefully.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    import orjson

    _loads = orjson.loads

    def _dumps(obj: object) -> str:
        return orjson.dumps(obj).decode()
except ImportError:
    import json

    _loads = json.loads

    def _dumps(obj: object) -> str:
        return json.dumps(obj)


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def git_changed_files(base_ref: str, pattern: str) -> list[str]:
    """Get changed files matching pattern between base_ref and HEAD."""
    for sep in ("...", " "):
        r = run(["git", "diff", "--name-only", "--diff-filter=ACMR",
                 f"{base_ref}{'...' if sep == '...' else ''}HEAD" if sep == "..." else base_ref,
                 *([] if sep == "..." else ["HEAD"]),
                 "--", pattern])
        if r.returncode == 0 and r.stdout.strip():
            return [f for f in r.stdout.strip().splitlines() if f]
    return []


def extract_diff_ranges(base_ref: str, *patterns: str) -> dict[str, list[list[int]]]:
    """Parse diff hunks to get new-file line ranges per changed file."""
    pat_args = ["--"] + list(patterns) if patterns else ["--", "*.py"]
    r = run(["git", "diff", "-U0", f"{base_ref}...HEAD", *pat_args])
    if r.returncode != 0:
        r = run(["git", "diff", "-U0", base_ref, "HEAD", *pat_args])

    hunk_re = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
    ranges: dict[str, list[list[int]]] = {}
    current_file = None
    for line in r.stdout.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
        elif line.startswith("@@") and current_file:
            m = hunk_re.match(line)
            if m:
                start = int(m.group(1))
                count = int(m.group(2)) if m.group(2) else 1
                if count > 0:
                    ranges.setdefault(current_file, []).append(
                        [start, start + count - 1]
                    )
    return ranges


def in_range(
    filepath: str, line: int, ranges: dict[str, list[list[int]]], repo_root: str
) -> bool:
    rel = os.path.relpath(filepath, repo_root) if os.path.isabs(filepath) else filepath
    return any(s <= line <= e for s, e in ranges.get(rel, []))


# ---------------------------------------------------------------------------
# Tool runners
# ---------------------------------------------------------------------------

def run_ruff_lint(changed_py: list[str], ranges: dict, repo_root: str) -> dict:
    if not shutil.which("ruff"):
        return {"skipped": True, "reason": "ruff not installed"}

    r = run([
        "ruff", "check", "--output-format=json",
        "--extend-select", "PLR",
        "--config", "lint.pylint.max-args=10",
        "--config", "lint.pylint.max-locals=25",
        "--config", "lint.pylint.max-statements=40",
        *changed_py,
    ])
    try:
        findings = _loads(r.stdout)
    except (ValueError, TypeError):
        return {"exit_code": r.returncode, "output": [], "error": r.stderr}

    original = len(findings)
    filtered = [
        f for f in findings
        if in_range(f.get("filename", ""), f.get("location", {}).get("row", 0),
                    ranges, repo_root)
    ]
    return {
        "exit_code": 0 if not filtered else r.returncode,
        "output": filtered,
        "filtered": original - len(filtered),
    }


def run_ruff_format(changed_py: list[str]) -> dict:
    if not shutil.which("ruff"):
        return {"skipped": True, "reason": "ruff not installed"}

    r = run(["ruff", "format", "--check", "--diff", *changed_py])
    return {"exit_code": r.returncode, "output": r.stdout}


def run_bandit(changed_py: list[str], ranges: dict, repo_root: str) -> dict:
    if not shutil.which("bandit"):
        return {"skipped": True, "reason": "bandit not installed"}

    r = run(["bandit", "-q", "-f", "json", *changed_py])
    try:
        output = _loads(r.stdout)
    except (ValueError, TypeError):
        return {"exit_code": r.returncode, "output": {"results": []}, "error": r.stderr}

    results = output.get("results", [])
    original = len(results)
    output["results"] = [
        f for f in results
        if in_range(f.get("filename", ""), f.get("line_number", 0), ranges, repo_root)
    ]
    return {
        "exit_code": 0 if not output["results"] else r.returncode,
        "output": output,
        "filtered": original - len(output["results"]),
    }


def run_towncrier(base_ref: str) -> dict:
    has_fragments = any(
        Path(d).is_dir() for d in ("newsfragments", "changelog.d", "changes")
    )
    if not has_fragments:
        return {"skipped": True, "reason": "no newsfragments directory"}
    if not shutil.which("towncrier"):
        return {"skipped": True, "reason": "towncrier not installed"}

    r = run(["towncrier", "check", "--compare-with", base_ref])
    missing = r.returncode != 0
    return {"exit_code": r.returncode, "missing": missing, "output": r.stdout + r.stderr}


def run_griffe(base_ref: str, head_ref: str, repo_root: str) -> dict:
    try:
        from griffe import find_breaking_changes, load_git
    except ImportError:
        return {"skipped": True, "reason": "griffe not installed"}

    src_dir = os.path.join(repo_root, "src")
    if os.path.isdir(src_dir):
        search_paths = ["src"]
        scan_dir = src_dir
    else:
        search_paths = ["."]
        scan_dir = repo_root

    packages = []
    namespace_packages = []
    for entry in sorted(os.listdir(scan_dir)):
        entry_path = os.path.join(scan_dir, entry)
        if not os.path.isdir(entry_path):
            continue
        if entry.startswith(("test", ".", "_")):
            continue
        if entry in ("docs", "scripts", "benchmarks", "newsfragments"):
            continue
        if entry.endswith((".egg-info", ".dist-info")):
            continue
        if os.path.isfile(os.path.join(entry_path, "__init__.py")):
            packages.append(entry)
        elif any(f.endswith(".py") for f in os.listdir(entry_path)):
            namespace_packages.append(entry)

    results: dict = {"packages": {}}
    for pkg in packages:
        try:
            old = load_git(pkg, ref=base_ref, search_paths=search_paths)
            new = load_git(pkg, ref=head_ref, search_paths=search_paths)
            breakages = [str(b) for b in find_breaking_changes(old, new)]
            results["packages"][pkg] = {"breaking_changes": breakages, "skipped": False}
        except (ImportError, ModuleNotFoundError) as e:
            results["packages"][pkg] = {
                "breaking_changes": [], "skipped": True, "reason": str(e),
            }
        except Exception as e:
            results["packages"][pkg] = {
                "breaking_changes": [], "skipped": True, "reason": f"unexpected: {e}",
            }

    for pkg in namespace_packages:
        results["packages"][pkg] = {
            "breaking_changes": [], "skipped": True,
            "reason": "namespace package (no __init__.py); needs manual diff review",
        }

    if not packages and not namespace_packages:
        results["skipped"] = True
        results["reason"] = "no Python packages found"

    return results


def run_cargo_fmt(repo_root: str) -> dict:
    """Run cargo fmt --check on the workspace."""
    cargo_toml = os.path.join(repo_root, "Cargo.toml")
    if not os.path.isfile(cargo_toml):
        return {"skipped": True, "reason": "no Cargo.toml"}
    if not shutil.which("cargo"):
        return {"skipped": True, "reason": "cargo not installed"}

    r = run(["cargo", "fmt", "--check"], cwd=repo_root)
    return {"exit_code": r.returncode, "output": r.stdout + r.stderr}


def run_clippy(changed_rs: list[str], ranges: dict, repo_root: str) -> dict:
    """Run cargo clippy on Rust files, filtering to diff-touched lines."""
    cargo_toml = os.path.join(repo_root, "Cargo.toml")
    if not os.path.isfile(cargo_toml):
        return {"skipped": True, "reason": "no Cargo.toml"}
    if not shutil.which("cargo"):
        return {"skipped": True, "reason": "cargo not installed"}

    r = run(["cargo", "clippy", "--message-format=json", "--quiet", "--"],
            cwd=repo_root)
    findings = []
    for line in r.stdout.splitlines():
        try:
            msg = _loads(line)
        except (ValueError, TypeError):
            continue
        if msg.get("reason") != "compiler-message":
            continue
        cm = msg.get("message", {})
        level = cm.get("level", "")
        if level not in ("warning", "error"):
            continue
        spans = cm.get("spans", [])
        primary = next((s for s in spans if s.get("is_primary")), None)
        if not primary:
            continue
        filepath = primary.get("file_name", "")
        line_num = primary.get("line_start", 0)
        if not in_range(filepath, line_num, ranges, repo_root):
            continue
        findings.append({
            "level": level,
            "code": cm.get("code", {}).get("code", "") if cm.get("code") else "",
            "message": cm.get("message", ""),
            "file": filepath,
            "line_start": line_num,
            "line_end": primary.get("line_end", line_num),
        })

    return {
        "exit_code": 0 if not findings else 1,
        "output": findings,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: static-analysis.py <base_ref> [repo_root] [output_dir]", file=sys.stderr)
        sys.exit(1)

    base_ref = sys.argv[1]
    repo_root = sys.argv[2] if len(sys.argv) > 2 else "."
    outdir = sys.argv[3] if len(sys.argv) > 3 else tempfile.mkdtemp(prefix="static-analysis-")
    os.makedirs(outdir, exist_ok=True)
    os.chdir(repo_root)

    head_ref = run(["git", "rev-parse", "HEAD"]).stdout.strip()
    changed_py = git_changed_files(base_ref, "*.py")
    changed_rs = git_changed_files(base_ref, "*.rs")

    if not changed_py and not changed_rs:
        Path(outdir, "static-analysis.json").write_text(_dumps({
            "changed_py_files": [], "changed_rs_files": [],
            "ruff_lint": None, "ruff_format": None,
            "bandit": None, "towncrier": None, "griffe": None,
            "clippy": None,
            "cargo_fmt": None,
        }))
        print(outdir)
        return

    futures = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        if changed_py:
            py_ranges = extract_diff_ranges(base_ref, "*.py")
            futures["ruff_lint"] = pool.submit(run_ruff_lint, changed_py, py_ranges, repo_root)
            futures["ruff_format"] = pool.submit(run_ruff_format, changed_py)
            futures["bandit"] = pool.submit(run_bandit, changed_py, py_ranges, repo_root)
            futures["griffe"] = pool.submit(run_griffe, base_ref, head_ref, repo_root)
        futures["towncrier"] = pool.submit(run_towncrier, base_ref)
        if changed_rs:
            rs_ranges = extract_diff_ranges(base_ref, "*.rs")
            futures["clippy"] = pool.submit(run_clippy, changed_rs, rs_ranges, repo_root)
            futures["cargo_fmt"] = pool.submit(run_cargo_fmt, repo_root)

    result = {
        "changed_py_files": changed_py,
        "changed_rs_files": changed_rs,
        "ruff_lint": futures["ruff_lint"].result() if "ruff_lint" in futures else None,
        "ruff_format": futures["ruff_format"].result() if "ruff_format" in futures else None,
        "bandit": futures["bandit"].result() if "bandit" in futures else None,
        "towncrier": futures["towncrier"].result(),
        "griffe": futures["griffe"].result() if "griffe" in futures else None,
        "clippy": futures["clippy"].result() if "clippy" in futures else None,
        "cargo_fmt": futures["cargo_fmt"].result() if "cargo_fmt" in futures else None,
    }

    Path(outdir, "static-analysis.json").write_text(_dumps(result))
    print(outdir)


if __name__ == "__main__":
    main()
