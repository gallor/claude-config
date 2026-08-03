#!/usr/bin/env python3
"""Deterministic review triage: shape (trivial?) + surface (which aspects) signals.

Usage: triage.py <base_ref> [repo_root] [output_dir]

  base_ref    Git ref to diff against (e.g. origin/main, HEAD~1, abc123)
  repo_root   Repository root directory. Default: cwd.
  output_dir  Where to write output. Default: mktemp -d.

Writes:
  triage.json  - {trivial, surfaces{compat,tests,docs,perf}, files[]}
                 (files[] is a per-file debug aid; consumers read trivial + surfaces)

Prints the output directory path to stdout.

This replaces the `git diff --stat` line-count heuristic in review/SKILL.md step 2b
and the pr-pipeline step 1 gate. It answers two distinct questions from ONE diff walk:

  SHAPE (the `trivial` bit): is there any real code change, or is the diff
    prose/config/pure-mechanical? Trivial <=> no logic touched, at ANY size. This is
    the primary gate: a 1-line `if x` -> `if x or True` is NOT trivial; a 500-line
    rename IS. Diff size is not consulted. Python shape is decided by AST equality
    (ignores whitespace/comments, preserves block structure).

  SURFACE (the `surfaces` map): which DETERMINISTIC step-4 aspect triggers fired --
    compat (__all__ / new required param), tests (test file touched), docs (doc
    globs / added docstrings), perf (benchmarks/ touched). These are pre-computed
    here as facts so the review reads booleans instead of re-deriving them. SEMANTIC
    triggers (security "is this auth code", simplify "new capability", premise
    "human objected", perf "serde code / known hot path") are NOT computed here --
    they stay model judgment. This script is deterministic-only, by design.

Fail-safe rule: anything we cannot classify deterministically (non-Python source,
unparseable Python, unknown extension with content, an unresolvable base ref)
yields trivial=false (full panel). The gate never under-reviews; the worst case is
a wasted panel.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import orjson

    def _dumps(obj: object) -> str:
        return orjson.dumps(obj, option=orjson.OPT_INDENT_2).decode()
except ImportError:
    import json

    def _dumps(obj: object) -> str:
        return json.dumps(obj, indent=2)


# --- extension / path classification -------------------------------------------

# Content whose change is never "code logic" for triage: prose, docs, config, data.
PROSE_CONFIG_EXT = frozenset(
    {
        ".md",
        ".rst",
        ".txt",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".json",
        ".lock",
    }
)
PY_EXT = frozenset({".py", ".pyi"})
# Real logic, but no stdlib tokenizer here -> fail safe to panel on any code change.
OTHER_CODE_EXT = frozenset(
    {
        ".rs",
        ".cpp",
        ".hpp",
        ".h",
        ".cc",
        ".c",
        ".cxx",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".go",
        ".java",
        ".sh",
        ".bash",
    }
)
# Directories whose files are towncrier fragments regardless of extension
# (fragment *types* are per-repo configurable: .bugfix/.feature/.removal/.misc/.md/...).
NEWSFRAGMENT_DIRS = frozenset({"newsfragments", "changelog.d", "changes"})

DOC_EXT = frozenset({".md", ".rst", ".txt"})


def _ext(path: str) -> str:
    dot = path.rfind(".")
    slash = path.rfind("/")
    return path[dot:] if dot > slash else ""


def _is_newsfragment(path: str) -> bool:
    return any(p in NEWSFRAGMENT_DIRS for p in path.split("/"))


def _is_test_file(path: str) -> bool:
    base = path.rsplit("/", 1)[-1]
    return (
        base.startswith("test_")
        or base.endswith("_test.py")
        or "/tests/" in f"/{path}"
        or base == "conftest.py"
    )


# --- git plumbing --------------------------------------------------------------


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


class RefUnresolved(RuntimeError):
    """The base ref could not be resolved by any diff form (distinct from empty diff)."""


def _changed_files(base_ref: str) -> list[tuple[str, str, str | None]]:
    """Return [(status, new_path, old_path)] for changed files. status in ACMRD.

    `old_path` is set only for renames (`R`); None otherwise — so a content-identical
    rename can compare old→new content and classify trivial.

    Raises `RefUnresolved` when **no** diff form succeeds (unfetched/stale ref, git
    error). This is deliberately distinct from a genuinely empty diff (a form
    succeeded with no output → `[]`): an empty result and a resolution failure must
    not look identical, or a can't-resolve-the-ref failure would silently classify
    as trivial (fail *unsafe*). The caller fails safe on `RefUnresolved`.
    """
    resolved = False
    for triple in (True, False):
        ref = f"{base_ref}...HEAD" if triple else base_ref
        args = ["git", "diff", "--name-status", "--diff-filter=ACMRD", ref]
        if not triple:
            args.append("HEAD")
        r = _run(args)
        if r.returncode != 0:
            continue
        resolved = True
        out = []
        for line in r.stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            status = parts[0][0]
            if status == "R" and len(parts) >= 3:
                out.append((status, parts[2], parts[1]))  # (R, new, old)
            else:
                out.append((status, parts[-1], None))
        return out
    if not resolved:
        raise RefUnresolved(f"could not resolve base ref {base_ref!r}")
    return []


def _file_at(ref: str, path: str) -> str | None:
    """Contents of path at ref, or None if absent (add/delete)."""
    r = _run(["git", "show", f"{ref}:{path}"])
    return r.stdout if r.returncode == 0 else None


def _diff_added_lines(base_ref: str, path: str) -> list[str]:
    """The '+' lines added to `path` (for docstring / import detection)."""
    for ref in (f"{base_ref}...HEAD", base_ref):
        r = _run(
            ["git", "diff", "-U0", ref, *([] if "..." in ref else ["HEAD"]), "--", path]
        )
        if r.returncode == 0 and r.stdout:
            return [
                line[1:]
                for line in r.stdout.splitlines()
                if line.startswith("+") and not line.startswith("+++")
            ]
    return []


# --- shape axis: AST comparison ------------------------------------------------


def _ast_repr(src: str) -> str | None:
    """`ast.dump` of the parsed module, or None if unparseable.

    AST equality is the right granularity for shape: it ignores whitespace,
    indentation *width*, blank lines, and comments (none survive parse), so pure
    reformat/reindent compares equal (trivial) — but it PRESERVES block structure,
    so moving a statement in/out of an `if`/`try`/loop is a change (panel). A flat
    token stream can't see block membership (INDENT/DEDENT must be stripped to make
    reformat trivial, but those are the only tokens encoding nesting) — the gap that
    let an indentation-only control-flow change read as trivial. String *values* are
    kept, so a docstring/literal change is a change (safe side).
    """
    try:
        return ast.dump(ast.parse(src))
    except (SyntaxError, ValueError):
        return None


def _py_code_changed(before: str | None, after: str | None) -> tuple[bool, str]:
    """(changed, reason) for a Python file. Whole-file AST comparison."""
    if before is None or after is None:
        # Pure add or delete of a .py file is a code change unless the file is empty.
        content = after if before is None else before
        if content is not None and _ast_repr(content) == _ast_repr(""):
            return False, "py empty add/delete"
        return True, "py file added/removed"
    ba = _ast_repr(before)
    aa = _ast_repr(after)
    if ba is None or aa is None:
        return True, "py unparseable -> fail-safe"
    if ba == aa:
        return False, "py no AST change (reformat/comment/whitespace)"
    return True, "py code change"


# --- surface axis: deterministic step-4 triggers -------------------------------


def _public_symbols_or_required_params_changed(
    base_ref: str, py_files: list[tuple[str, str | None]]
) -> bool:
    """compat surface: __all__ line touched, or a new REQUIRED param on an existing def.

    Deterministic subset of the compat trigger (the semantic 'is this a public API'
    judgment stays with the model). Conservative: any added line containing the token
    `__all__`, or any function whose required-arg count grew. Rename-aware — reads
    base content from the old path so a rename+new-required-param in one commit fires.
    """
    for path, old_path in py_files:
        added = _diff_added_lines(base_ref, path)
        if any("__all__" in line for line in added):
            return True
        before = _file_at(base_ref, old_path or path)
        after_p = Path(path)
        after = after_p.read_text() if after_p.is_file() else None
        if before is None or after is None:
            continue
        try:
            b_reqs = _required_params(before)
            a_reqs = _required_params(after)
        except SyntaxError:
            continue
        for name, n in a_reqs.items():
            if name in b_reqs and n > b_reqs[name]:
                return True
    return False


def _required_params(src: str) -> dict[str, int]:
    """Map qualified function name -> count of required positional/kw params."""
    tree = ast.parse(src)
    out: dict[str, int] = {}

    class V(ast.NodeVisitor):
        def __init__(self):
            self.stack: list[str] = []

        def _visit_fn(self, node):
            a = node.args
            required = len(a.posonlyargs) + len(a.args) - len(a.defaults)
            required += sum(1 for d in a.kw_defaults if d is None)
            qual = ".".join([*self.stack, node.name])
            out[qual] = required
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        visit_FunctionDef = _visit_fn
        visit_AsyncFunctionDef = _visit_fn

        def visit_ClassDef(self, node):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

    V().visit(tree)
    return out


def _has_added_docstring(base_ref: str, py_files: list[tuple[str, str | None]]) -> bool:
    for path, _old in py_files:
        for line in _diff_added_lines(base_ref, path):
            s = line.lstrip()
            if s.startswith(('"""', "'''", 'r"""', "r'''")):
                return True
    return False


# --- main ----------------------------------------------------------------------


def triage(base_ref: str, repo_root: str) -> dict:
    os.chdir(repo_root)
    try:
        changed = _changed_files(base_ref)
    except RefUnresolved as e:
        # Can't even enumerate the diff -> fail safe (never silently "trivial").
        return {
            "trivial": False,
            "surfaces": {"compat": False, "tests": False, "docs": False, "perf": False},
            "files": [],
            "error": str(e),
        }

    files_report: list[dict] = []
    trivial = True

    # (new_path, old_path) so surface helpers can read base content across a rename.
    py_files = [
        (p, o) for _s, p, o in changed if _ext(p) in PY_EXT and Path(p).is_file()
    ]
    all_changed = [p for _s, p, _o in changed]

    for status, path, old_path in changed:
        e = _ext(path)
        if _is_newsfragment(path):
            v, why = False, "newsfragment (dir-based)"
        elif e in PROSE_CONFIG_EXT:
            v, why = False, f"prose/config ({e})"
        elif e in PY_EXT:
            # For a rename, read the OLD content from its OLD path — else a
            # content-identical rename reads as an add (old path absent at base).
            before = _file_at(base_ref, old_path or path)
            after = Path(path).read_text() if Path(path).is_file() else None
            v, why = _py_code_changed(before, after)
        elif e in OTHER_CODE_EXT:
            # No stdlib tokenizer for non-Python source, and a comment/blank-strip
            # heuristic can't safely tell logic from comments across languages
            # (`#` is a comment in shell but a preprocessor/attribute directive in
            # C/Rust). Fail safe: any change to non-Python source gets the panel.
            # This is sound because non-Python trivial diffs don't occur in practice
            # (Rust source edits are never trivial-sized — Tier B rejected, #98).
            v, why = True, f"{e} non-python source -> fail-safe"
        elif not e:
            # Extension-less (scripts, data) -> fail safe if it has content.
            v, why = True, "no extension -> fail-safe"
        else:
            v, why = True, f"unknown ext ({e}) -> fail-safe"
        files_report.append(
            {"path": path, "status": status, "code_change": v, "reason": why}
        )
        if v:
            trivial = False

    surfaces = {
        "compat": _public_symbols_or_required_params_changed(base_ref, py_files),
        "tests": any(_is_test_file(p) for p in all_changed),
        "docs": (
            any(_ext(p) in DOC_EXT or _is_newsfragment(p) for p in all_changed)
            or _has_added_docstring(base_ref, py_files)
        ),
        # Only the high-precision benchmarks/ signal is deterministic. "Serialization
        # code changed" stays a SEMANTIC step-4 trigger (the model judges whether serde
        # *logic* changed) — an appearing `import json` is too common to spawn a perf
        # agent on (low precision, real round-trip cost).
        "perf": any(
            "/benchmarks/" in f"/{p}" or p.startswith("benchmarks/")
            for p in all_changed
        ),
    }

    # `files` is retained as a debug aid (per-file verdict + reason) for when the
    # gate mis-routes and someone needs to see why. Consumers read only `.trivial`
    # and `.surfaces.*`.
    return {
        "trivial": trivial,
        "surfaces": surfaces,
        "files": files_report,
    }


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: triage.py <base_ref> [repo_root] [output_dir]", file=sys.stderr)
        sys.exit(1)
    base_ref = sys.argv[1]
    repo_root = sys.argv[2] if len(sys.argv) > 2 else "."
    outdir = sys.argv[3] if len(sys.argv) > 3 else tempfile.mkdtemp(prefix="triage-")
    os.makedirs(outdir, exist_ok=True)

    result = triage(base_ref, os.path.abspath(repo_root))
    Path(outdir, "triage.json").write_text(_dumps(result))
    print(outdir)


if __name__ == "__main__":
    main()
