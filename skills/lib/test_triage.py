#!/usr/bin/env python3
"""Tests for triage.py's risk-shape + surface classification (claude-config#98).

Run: python3 -m pytest this file, or execute directly. No external deps — builds
tiny synthetic git repos and drives the script as a subprocess, exactly as the
review skill does. Covers the load-bearing, drift-prone classification logic:
shape (prose/reformat/logic), fail-safe (non-Python/unknown), newsfragment-by-dir,
pure deletion, and the deterministic surface signals.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).with_name("triage.py")


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _triage(base_files, head_files, renames=None):
    """Build a 2-commit repo (base -> head) and return triage.json as a dict.

    base_files / head_files: {path: content|None}. None in head deletes the file.
    A path present only in head is an add.
    renames: optional [(old_path, new_path)] applied via `git mv` (no content change).
    """
    with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as out:
        _git(repo, "init", "-q")
        _git(repo, "config", "user.email", "t@t")
        _git(repo, "config", "user.name", "t")
        for path, content in base_files.items():
            p = Path(repo, path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "--allow-empty", "-m", "base")
        base_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
        ).stdout.strip()
        for old, new in renames or []:
            _git(repo, "mv", old, new)
        # apply head changes
        for path, content in head_files.items():
            p = Path(repo, path)
            if content is None:
                if p.exists():
                    p.unlink()
                continue
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "--allow-empty", "-m", "head")
        subprocess.run(
            [sys.executable, str(SCRIPT), base_sha, repo, out],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(Path(out, "triage.json").read_text())


# --- shape axis ----------------------------------------------------------------


def test_prose_only_is_trivial():
    r = _triage({"README.md": "# Hi\n"}, {"README.md": "# Hi\n\nmore words\n"})
    assert r["trivial"] is True


def test_config_yaml_is_trivial():
    r = _triage({"ci.yaml": "on: push\n"}, {"ci.yaml": "on: push\njobs: {}\n"})
    assert r["trivial"] is True


def test_python_logic_change_is_not_trivial():
    """The dangerous case: a 1-line logic edit must NOT be trivial."""
    r = _triage(
        {"a.py": "def f(x):\n    return x\n"},
        {"a.py": "def f(x):\n    return x or True\n"},
    )
    assert r["trivial"] is False


def test_python_boundary_operator_change_is_not_trivial():
    r = _triage(
        {"a.py": "def f(x):\n    return x < 5\n"},
        {"a.py": "def f(x):\n    return x <= 5\n"},
    )
    assert r["trivial"] is False


def test_python_constant_change_is_not_trivial():
    r = _triage(
        {"a.py": "TIMEOUT = 30\n"},
        {"a.py": "TIMEOUT = 300\n"},
    )
    assert r["trivial"] is False


def test_python_reformat_only_is_trivial():
    """Pure whitespace/reindent (identical token stream) is trivial."""
    r = _triage(
        {"a.py": "def f(x):\n    return x+1\n"},
        {"a.py": "def f(x):\n    return x + 1\n"},
    )
    assert r["trivial"] is True


def test_python_comment_only_is_trivial():
    r = _triage(
        {"a.py": "x = 1\n"},
        {"a.py": "x = 1  # a comment\n"},
    )
    assert r["trivial"] is True


def test_python_block_membership_change_is_not_trivial():
    """Critical regression: moving a statement out of an `if` block is a logic change.

    Only indentation changes (statement tokens identical), so a flat token-stream
    check read it as trivial — an under-review of a control-flow edit. AST comparison
    preserves block structure and catches it.
    """
    r = _triage(
        {"a.py": "def h(a):\n    if a:\n        f()\n        g()\n"},
        {"a.py": "def h(a):\n    if a:\n        f()\n    g()\n"},
    )
    assert r["trivial"] is False


def test_python_content_identical_rename_is_trivial():
    """The docstring's headline example: a pure rename (no content change) is trivial."""
    r = _triage(
        {"pkg/a.py": "def f():\n    return 1\n"},
        {},
        renames=[("pkg/a.py", "pkg/b.py")],
    )
    assert r["trivial"] is True


def test_python_docstring_edit_is_not_trivial():
    """A docstring is a STRING token — changing it is a (safe-side) code change.

    We intentionally treat string-literal changes as non-trivial rather than
    reverse-engineer intent; over-review, never under-review.
    """
    r = _triage(
        {"a.py": 'def f():\n    """old."""\n    return 1\n'},
        {"a.py": 'def f():\n    """new wording."""\n    return 1\n'},
    )
    assert r["trivial"] is False


# --- fail-safe -----------------------------------------------------------------


def test_rust_change_fails_safe_to_panel():
    """No stdlib tokenizer for Rust -> any non-comment change is non-trivial."""
    r = _triage(
        {"a.rs": "fn f() -> i32 { 1 }\n"},
        {"a.rs": "fn f() -> i32 { 2 }\n"},
    )
    assert r["trivial"] is False


def test_rust_any_change_fails_safe():
    """Non-Python fails safe unconditionally — even a comment-only change panels.

    We do NOT try to strip comments from non-Python source: `#` is a comment in
    shell but a preprocessor/attribute directive in C/Rust, so a strip heuristic
    would misclassify a `#define`/`#[attr]` logic change as trivial (the fail-safe
    violation caught in review). Over-review is the correct tradeoff — non-Python
    trivial diffs don't occur in practice (Tier B rejected, #98).
    """
    r = _triage(
        {"a.rs": "fn f() {}\n"},
        {"a.rs": "fn f() {}\n// note\n"},
    )
    assert r["trivial"] is False


def test_c_define_only_change_fails_safe():
    """Regression for the fail-safe violation: a C macro-constant change is logic.

    `#define MAX 5` -> `500` with an unchanged function body was misclassified
    trivial by the old comment-strip heuristic (`#`-lines dropped as comments),
    routing a logic change to the inline path. Non-Python now fails safe.
    """
    r = _triage(
        {"a.c": "#define MAX 5\nint f(void) { return MAX; }\n"},
        {"a.c": "#define MAX 500\nint f(void) { return MAX; }\n"},
    )
    assert r["trivial"] is False


def test_unknown_extension_with_content_fails_safe():
    r = _triage({"data.bin": "a\n"}, {"data.bin": "b\n"})
    assert r["trivial"] is False


# --- newsfragments (directory-based, not extension-based) -----------------------


def test_newsfragment_md_is_trivial():
    r = _triage({}, {"newsfragments/12.feature.md": "Added a thing.\n"})
    assert r["trivial"] is True


def test_newsfragment_custom_type_is_trivial():
    """A .bugfix / .misc fragment has an 'unknown' extension but lives in the dir."""
    r = _triage({}, {"newsfragments/12.bugfix": "Fixed a thing.\n"})
    assert r["trivial"] is True
    assert r["surfaces"]["docs"] is True


# --- pure deletion (prototype false-positived this; must be trivial) -----------


def test_pure_config_deletion_is_trivial():
    r = _triage(
        {"conda-recipe/meta.yaml": "package: x\n"},
        {"conda-recipe/meta.yaml": None},
    )
    assert r["trivial"] is True


# --- surface signals -----------------------------------------------------------


def test_surface_tests_fires_on_test_file():
    r = _triage(
        {"tests/test_a.py": "def test_x():\n    assert True\n"},
        {"tests/test_a.py": "def test_x():\n    assert 1 == 1\n"},
    )
    assert r["surfaces"]["tests"] is True


def test_surface_compat_fires_on_all_change():
    r = _triage(
        {"m.py": "__all__ = ['a']\na = 1\n"},
        {"m.py": "__all__ = ['a', 'b']\na = 1\nb = 2\n"},
    )
    assert r["surfaces"]["compat"] is True


def test_surface_compat_fires_on_new_required_param():
    r = _triage(
        {"m.py": "def f(a):\n    return a\n"},
        {"m.py": "def f(a, b):\n    return a + b\n"},
    )
    assert r["surfaces"]["compat"] is True


def test_surface_compat_quiet_on_new_optional_param():
    """Adding a param WITH a default is not a required-param break."""
    r = _triage(
        {"m.py": "def f(a):\n    return a\n"},
        {"m.py": "def f(a, b=1):\n    return a + b\n"},
    )
    assert r["surfaces"]["compat"] is False


def test_surface_perf_fires_on_benchmarks_touch():
    r = _triage(
        {"benchmarks/bench_x.py": "def bench():\n    pass\n"},
        {"benchmarks/bench_x.py": "def bench():\n    return 1\n"},
    )
    assert r["surfaces"]["perf"] is True


def test_surface_perf_quiet_on_serde_import():
    """A serde import alone does NOT fire perf — that's a semantic step-4 call.

    `import json` is too common to spawn a perf agent on; whether serialization
    logic changed is judged by the model, not this deterministic pass.
    """
    r = _triage(
        {"m.py": "x = 1\n"},
        {"m.py": "import orjson\nx = 1\n"},
    )
    assert r["surfaces"]["perf"] is False


def test_surface_docs_fires_on_added_docstring():
    r = _triage(
        {"m.py": "def f():\n    return 1\n"},
        {"m.py": 'def f():\n    """Do it."""\n    return 1\n'},
    )
    assert r["surfaces"]["docs"] is True


def test_surface_compat_fires_on_rename_plus_new_required_param():
    """compat must fire when a git-detected rename ALSO gains a required param.

    The helper reads base content from the OLD path; without rename-awareness the
    base read returns None (new path absent at base) and the required-param check is
    skipped, silently under-firing compat. Needs a file substantial enough that git
    detects the rename (`R`) rather than delete+add — a signature change on a tiny
    file drops below git's similarity threshold and becomes D+A, which has no
    old→new linkage for *any* deterministic pass (it falls to the semantic fallback).
    """
    base_body = (
        "def f(a):\n    return a\n\n"
        "def g(x):\n    return x * 2\n\n"
        "def h(y):\n    return y + 1\n"
    )
    head_body = base_body.replace(
        "def f(a):\n    return a\n", "def f(a, b):\n    return a + b\n"
    )
    r = _triage(
        {"pkg/a.py": base_body},
        {"pkg/b.py": head_body},
        renames=[("pkg/a.py", "pkg/b.py")],
    )
    assert r["surfaces"]["compat"] is True


# --- multi-file aggregation ----------------------------------------------------


def test_mixed_prose_and_logic_change_is_not_trivial():
    """`trivial ⇔ no logic at ANY size` — a trivial file must not mask a logic file.

    Guards the per-file `any(code_change)` aggregation against a last-file-wins
    mutation (`trivial = not v`). git enumerates changed files in path order, so the
    trivial file must sort **after** the logic file for the mutant to misclassify —
    `a.py` (logic) then `z_notes.md` (prose): last-file-wins would read the prose
    file's `v=False` and wrongly return trivial. A `README.md`/`a.py` pairing would
    sort the `.py` last and mask the mutant, which is exactly the vacuous test kaa
    flagged.
    """
    r = _triage(
        {"a.py": "def f(x):\n    return x\n", "z_notes.md": "# n\n"},
        {"a.py": "def f(x):\n    return x or True\n", "z_notes.md": "# n\n\nmore\n"},
    )
    assert r["trivial"] is False


def test_both_sides_unparseable_fails_safe():
    """The `py unparseable -> fail-safe` branch: both before and after invalid Python.

    Single-sided-invalid trips 'code change' via the plain None-vs-dump fallback, so
    only a double-sided-invalid case exercises the `ba is None or aa is None` guard.
    """
    r = _triage(
        {"a.py": "def f(:\n    pass\n"},
        {"a.py": "def g(:\n    pass\n"},
    )
    assert r["trivial"] is False


def test_unresolvable_base_ref_fails_safe():
    """A base ref that can't be resolved must fail safe (trivial=false), not look empty.

    Regression for the silent fail-unsafe: if git can't enumerate the diff at all, the
    result must be distinguishable from a genuinely empty diff — else a can't-resolve
    failure would classify as trivial and skip review.
    """
    with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as out:
        _git(repo, "init", "-q")
        _git(repo, "config", "user.email", "t@t")
        _git(repo, "config", "user.name", "t")
        Path(repo, "a.py").write_text("x = 1\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "base")
        subprocess.run(
            [sys.executable, str(SCRIPT), "origin/does-not-exist", repo, out],
            check=True,
            capture_output=True,
            text=True,
        )
        d = json.loads(Path(out, "triage.json").read_text())
        assert d["trivial"] is False
        assert "error" in d


if __name__ == "__main__":
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q", __file__]))
