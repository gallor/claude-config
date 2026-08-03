#!/usr/bin/env python3
"""Tests for stream-pretty.py's summary extraction (the two sink env vars +
the review-bot-vs-calibrate extraction modes). Run: python3 -m pytest this file,
or execute directly. No external deps — drives the script as a subprocess with
crafted stream-json on stdin, exactly as GitHub Actions does.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).with_name("stream-pretty.py")


def _msg(text):
    return json.dumps(
        {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}
    )


def _run(texts, env_extra):
    """Feed assistant text blocks through stream-pretty with env_extra set."""
    stdin = "\n".join(_msg(t) for t in texts)
    env = {**os.environ, **env_extra}
    subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=stdin,
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )


def _tool(name, **inp):
    return json.dumps(
        {
            "type": "assistant",
            "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]},
        }
    )


def _run_events(events, env_extra):
    """Feed raw event JSON lines; return (stdout, stderr)."""
    stdin = "\n".join(events)
    env = {**os.environ, **env_extra}
    r = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=stdin,
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    return r.stdout, r.stderr


def test_calibrate_path_broad_and_last_match():
    """With STREAM_SUMMARY_FILE set: match calibrator headers, take the LAST
    (an earlier '**complete.**' block must not win over the real summary)."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "s.md"
        _run(
            ["**complete.**", "## Calibration Sweep Results\n\n0 candidates."],
            {"STREAM_SUMMARY_FILE": str(out), "GITHUB_STEP_SUMMARY": ""},
        )
        assert out.read_text().startswith("## Calibration Sweep Results")


def test_review_bot_path_ignores_later_calibration_heading():
    """The finding: with only GITHUB_STEP_SUMMARY (review-bot path), a review
    body that QUOTES a '## Calibration' heading after its verdict must still
    extract the '## 🟢 Review:' block — narrow first-match, unchanged behavior."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "s.md"
        _run(
            ["## 🟢 Review: LGTM\n\nThe PR adds a ## Calibration Sweep section."],
            {"GITHUB_STEP_SUMMARY": str(out), "STREAM_SUMMARY_FILE": ""},
        )
        assert out.read_text().startswith("## 🟢 Review: LGTM")


def test_stream_summary_file_unset_writes_nothing():
    """No STREAM_SUMMARY_FILE => that sink is never created (review-bot no-op)."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "never.md"
        _run(
            ["## 🟢 Review: ok"], {"STREAM_SUMMARY_FILE": "", "GITHUB_STEP_SUMMARY": ""}
        )
        assert not out.exists()


# --- tool-call tally (always emitted) + command-body logging ------------------


def test_tool_tally_always_emitted_to_step_summary():
    """The tally line lands in $GITHUB_STEP_SUMMARY on every run, with correct
    per-tool counts + total, and reads AFTER the verdict (footer position)."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "s.md"
        events = [
            _tool("Bash", command="rg foo src/"),
            _tool("Bash", command="rg bar src/"),
            _tool("Read", file_path="a.py"),
            _tool("Task"),
            _msg("## 🟢 Review: APPROVE\nlgtm"),
        ]
        _run_events(
            events, {"GITHUB_STEP_SUMMARY": str(out), "STREAM_SUMMARY_FILE": ""}
        )
        body = out.read_text()
        assert "🔧 tool calls: Bash 2, Read 1, Task 1 (total 4)" in body
        # footer: tally comes after the verdict heading
        assert body.index("## 🟢 Review") < body.index("🔧 tool calls")


def test_tool_tally_emitted_without_summary_text():
    """Tool calls but no final summary block => tally still emits (slowness is
    only known post-hoc, so the count must be present on every run)."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "s.md"
        _run_events(
            [_tool("Bash", command="echo hi")],
            {"GITHUB_STEP_SUMMARY": str(out), "STREAM_SUMMARY_FILE": ""},
        )
        assert "🔧 tool calls: Bash 1 (total 1)" in out.read_text()


def test_tool_tally_to_stderr_when_no_summary_sink():
    """No $GITHUB_STEP_SUMMARY (interactive/local): tally still lands on stderr,
    never polluting stdout's rendered stream."""
    stdout, stderr = _run_events(
        [_tool("Bash", command="echo hi"), _tool("Read", file_path="x")],
        {"GITHUB_STEP_SUMMARY": "", "STREAM_SUMMARY_FILE": ""},
    )
    assert "🔧 tool calls: Bash 1, Read 1 (total 2)" in stderr
    assert "🔧 tool calls" not in stdout


def test_bash_command_body_logged():
    """Bash calls log the command's first line to stdout (auditable call pattern);
    other tools stay name-only."""
    stdout, _ = _run_events(
        [
            _tool("Bash", command="rg foo src/\necho second"),
            _tool("Read", file_path="a.py"),
        ],
        {"GITHUB_STEP_SUMMARY": "", "STREAM_SUMMARY_FILE": ""},
    )
    assert "$ Bash: rg foo src/" in stdout  # first line only
    assert "second" not in stdout  # subsequent lines dropped
    assert "📖 Read" in stdout and "Read:" not in stdout  # non-Bash name-only


def test_bash_leading_assignment_line_skipped():
    """A body opening with a bare `VAR=path` setup line logs the first OPERATIVE
    line (the grep/cat/gh), not the assignment — else the batchability signal is
    lost. This is the live #251 gather-phase pattern (`ROOT=...` then the work)."""
    stdout, _ = _run_events(
        [_tool("Bash", command="ROOT=/runner/_work/x/repo\ngrep -rn foo $ROOT")],
        {"GITHUB_STEP_SUMMARY": "", "STREAM_SUMMARY_FILE": ""},
    )
    assert "$ Bash: grep -rn foo $ROOT" in stdout
    assert "ROOT=/runner" not in stdout  # setup line hidden


def test_bash_multiple_leading_assignments_skipped():
    """Several stacked setup assignments (incl. `export`) are all skipped."""
    stdout, _ = _run_events(
        [_tool("Bash", command="export GH_HOST=h\nROOT=/r\ncat $ROOT/f.json")],
        {"GITHUB_STEP_SUMMARY": "", "STREAM_SUMMARY_FILE": ""},
    )
    assert "$ Bash: cat $ROOT/f.json" in stdout
    assert "GH_HOST" not in stdout


def test_bash_env_prefix_is_operative_not_skipped():
    """`TZ=UTC date ...` is an env-PREFIXED command, not a bare assignment — the
    `date` token remains, so the whole line is operative and must be shown even
    when a real second line follows (rules out the `first_nonblank` fallback
    masking a misclassified first line)."""
    stdout, _ = _run_events(
        [_tool("Bash", command="TZ=America/Chicago date '+%H:%M'\necho done")],
        {"GITHUB_STEP_SUMMARY": "", "STREAM_SUMMARY_FILE": ""},
    )
    assert "$ Bash: TZ=America/Chicago date '+%H:%M'" in stdout
    assert "echo done" not in stdout


def test_bash_command_substitution_assignment_is_operative():
    """`CID=$(gh api ...)` does the work IN the assignment — the `$(` disqualifies
    it as a bare-value assignment, so it is operative and shown. A trailing line
    proves the classification, not the fallback, is what shows it.

    Also the mirror of the prologue rule, and the `_ECHO_ONLY` path's coverage: the
    trailing `echo $CID` only *displays* the result, so the weak cmd-sub candidate
    correctly stays operative instead of yielding to the next line (contrast
    `test_cmdsub_assign_prologue_does_not_shadow_following_work`)."""
    stdout, _ = _run_events(
        [_tool("Bash", command="CID=$(gh api repos/o/r/issues/comments)\necho $CID")],
        {"GITHUB_STEP_SUMMARY": "", "STREAM_SUMMARY_FILE": ""},
    )
    assert "$ Bash: CID=$(gh api repos/o/r/issues/comments)" in stdout
    assert "echo $CID" not in stdout


def test_bash_niladic_command_substitution_is_operative():
    """`TMPFILE=$(mktemp)` has a real side effect but NO internal whitespace, so a
    `\\S*`-value regex mis-swallows it as setup — the same false-skip this fix
    targets for `ROOT=/path`, in a niladic command-substitution shape (kaa#103).

    Shown when no real command follows. When one does, that command is the operative
    line instead — see `test_cmdsub_assign_prologue_does_not_shadow_following_work`
    (the original form of this test asserted the opposite and hid every
    `CTX=$(cat state)` + real-work body in a kaa review log).

    The leading `cd /tmp` is load-bearing: it makes the assignment reachable only
    *after* a setup skip, so the classification is what selects it. With a
    single-line body the assertion holds on every path (`first_nonblank` fallback),
    which made this test vacuous — it stayed green both with `_CMDSUB_ASSIGN`
    disabled and with the pre-kaa#103 bare-`\\S*` bug reintroduced. With the setup
    line, that bug returns `cd /tmp` and the test correctly fails."""
    stdout, _ = _run_events(
        [_tool("Bash", command="cd /tmp\nTMPFILE=$(mktemp)")],
        {"GITHUB_STEP_SUMMARY": "", "STREAM_SUMMARY_FILE": ""},
    )
    assert "$ Bash: TMPFILE=$(mktemp)" in stdout
    assert "cd /tmp" not in stdout


def test_cmdsub_assign_prologue_does_not_shadow_following_work():
    """A `VAR=$(cmd)` PROLOGUE must not hide the real command on the next line.

    Regression for the shape that dominates real kaa review bodies: stash a path,
    then work with it. Measured in four run logs (camus-ws 7764082, chippy#1809,
    symbology#258, dropcopy#1745): the `VAR=$(cat <state-file>)` prologue appears
    **19 times**, the `VAR=$(mktemp)`-then-use shape **0 times** — so when the two
    interpretations collide, the prologue reading is the one that matches reality.
    Before this fix the log showed six identical `CONTEXT_DIR=$(cat …)` lines, each
    carrying 12-60s of think-time, which read as narration waste when every one was
    hiding a real read."""
    stdout, _ = _run_events(
        [
            _tool(
                "Bash",
                command='CONTEXT_DIR=$(cat /tmp/kaa_context_dir)\ncat "$CONTEXT_DIR/diff.patch"',
            )
        ],
        {"GITHUB_STEP_SUMMARY": "", "STREAM_SUMMARY_FILE": ""},
    )
    assert '$ Bash: cat "$CONTEXT_DIR/diff.patch"' in stdout
    assert "kaa_context_dir" not in stdout


def test_echo_wrapping_a_substitution_is_real_work_not_display():
    """`echo $(ls "$CTX")` RUNS a subprocess, so it is work — a weak cmd-sub prologue
    must not shadow it. Guards the `(?!.*\\$\\()` lookahead in `_ECHO_ONLY`: without it
    the char class only excluded backticks, so this resolved to the prologue."""
    stdout, _ = _run_events(
        [_tool("Bash", command='CTX=$(cat /tmp/ctx)\necho $(ls "$CTX")')],
        {"GITHUB_STEP_SUMMARY": "", "STREAM_SUMMARY_FILE": ""},
    )
    assert '$ Bash: echo $(ls "$CTX")' in stdout
    assert "/tmp/ctx" not in stdout


def test_stacked_cmdsub_assigns_show_the_last_not_the_prologue():
    """Two stacked `VAR=$(cmd)` lines with no strong line after: the terminal one is
    the work, the opener is the prologue. Guards tracking the LAST weak candidate."""
    stdout, _ = _run_events(
        [_tool("Bash", command='CTX=$(cat f)\nRESULT=$(grep -c pattern "$CTX/file")')],
        {"GITHUB_STEP_SUMMARY": "", "STREAM_SUMMARY_FILE": ""},
    )
    assert '$ Bash: RESULT=$(grep -c pattern "$CTX/file")' in stdout
    assert "cat f" not in stdout


def test_bash_backtick_substitution_is_operative():
    """Legacy backtick substitution `X=`cmd`` also runs a subprocess and must be
    treated as operative, not setup."""
    stdout, _ = _run_events(
        [_tool("Bash", command="SHA=`git rev-parse HEAD`\necho $SHA")],
        {"GITHUB_STEP_SUMMARY": "", "STREAM_SUMMARY_FILE": ""},
    )
    assert "$ Bash: SHA=`git rev-parse HEAD`" in stdout


def test_bash_url_valued_assignment_is_setup():
    """A value with `?`/`&`/`=` (a URL) is still a bare assignment — must be
    SKIPPED as setup, not shown (guards against a charset-narrowing over-fix)."""
    stdout, _ = _run_events(
        [_tool("Bash", command="URL=http://h/x?a=1&b=2\ncurl $URL")],
        {"GITHUB_STEP_SUMMARY": "", "STREAM_SUMMARY_FILE": ""},
    )
    assert "$ Bash: curl $URL" in stdout
    assert "URL=http" not in stdout


def test_bash_all_assignment_body_falls_back_to_first_line():
    """A body that is ONLY assignments (no operative line) still logs something —
    fall back to the first non-blank line rather than emitting a bare name."""
    stdout, _ = _run_events(
        [_tool("Bash", command="A=1\nB=2")],
        {"GITHUB_STEP_SUMMARY": "", "STREAM_SUMMARY_FILE": ""},
    )
    assert "$ Bash: A=1" in stdout


def test_bash_source_setup_line_skipped():
    """The kaa#36 pattern: a body opening with `source ~/.claude/skills/lib/
    gh-env.sh` on its own line logs the operative `gh` on line 2, not the source
    — each Bash call is a fresh shell so the bare source is inert-alone setup."""
    stdout, _ = _run_events(
        [
            _tool(
                "Bash",
                command="source ~/.claude/skills/lib/gh-env.sh\ngh pr view 36 --json state",
            )
        ],
        {"GITHUB_STEP_SUMMARY": "", "STREAM_SUMMARY_FILE": ""},
    )
    assert "$ Bash: gh pr view 36 --json state" in stdout
    assert "gh-env.sh" not in stdout  # source line hidden


def test_bash_cd_and_dot_setup_lines_skipped():
    """`cd <dir>` and the `.` source alias are also bare setup builtins."""
    stdout, _ = _run_events(
        [
            _tool("Bash", command="cd /tmp/pr-reviews/x\ncat metadata.json"),
            _tool("Bash", command=". ./env.sh\ngh api repos/o/r"),
        ],
        {"GITHUB_STEP_SUMMARY": "", "STREAM_SUMMARY_FILE": ""},
    )
    assert "$ Bash: cat metadata.json" in stdout
    assert "$ Bash: gh api repos/o/r" in stdout
    assert "cd /tmp" not in stdout and "env.sh" not in stdout


def test_bash_chained_setup_command_shown_in_full():
    """A setup builtin CHAINED to operative work (`cd /x && cat y`, `source e; gh`)
    carries the real call on the same line — it must be shown, not skipped, so the
    chaining-operator guard (`&&`/`;`/`|`) keeps it intact. Each body carries a
    trailing operative line so a false 'setup' classification of line 1 would drop
    it to line 2 and change the output (rules out the first_nonblank fallback)."""
    stdout, _ = _run_events(
        [
            _tool("Bash", command="cd /tmp/x && cat y\necho done"),
            _tool("Bash", command="source env.sh && gh pr view 36\necho done"),
            _tool("Bash", command="cd /x; ls\necho done"),  # ; chain
            _tool("Bash", command="source e | tee log\necho done"),  # | chain
        ],
        {"GITHUB_STEP_SUMMARY": "", "STREAM_SUMMARY_FILE": ""},
    )
    assert "$ Bash: cd /tmp/x && cat y" in stdout
    assert "$ Bash: source env.sh && gh pr view 36" in stdout
    assert "$ Bash: cd /x; ls" in stdout
    assert "$ Bash: source e | tee log" in stdout
    assert "echo done" not in stdout  # trailing line never surfaces = line 1 was shown


def test_bash_setup_verb_word_boundary():
    """`cdr`/`sourced`/`sourcefile` are NOT the `cd`/`source` builtins — a command
    that merely starts with those letters must be treated as operative. Trailing
    operative line so a misclassification as setup would surface line 2 instead."""
    stdout, _ = _run_events(
        [
            _tool("Bash", command="cdr build --out x\necho done"),
            _tool("Bash", command="sourced_fn arg\necho done"),
        ],
        {"GITHUB_STEP_SUMMARY": "", "STREAM_SUMMARY_FILE": ""},
    )
    assert "$ Bash: cdr build --out x" in stdout
    assert "$ Bash: sourced_fn arg" in stdout
    assert "echo done" not in stdout


def test_bash_source_command_substitution_is_operative():
    """`source $(locate_env_file)` RAN a subprocess — a niladic substitution with no
    internal whitespace must not be mis-skipped as setup (the #103 cmd-sub guard,
    mirrored into _SETUP_CMD). kaa#104 [issue]."""
    stdout, _ = _run_events(
        [
            _tool(
                "Bash", command="source $(locate_env_file)\ngh pr view 36 --json state"
            )
        ],
        {"GITHUB_STEP_SUMMARY": "", "STREAM_SUMMARY_FILE": ""},
    )
    assert "$ Bash: source $(locate_env_file)" in stdout
    assert "gh pr view" not in stdout  # line 1 was operative, shown; line 2 not reached


def test_bash_all_setup_lines_falls_back_to_first():
    """A body that is ONLY setup lines (assignment + source, no operative line)
    still logs something — the first non-blank line, never a bare name."""
    stdout, _ = _run_events(
        [_tool("Bash", command="ROOT=/x\nsource env.sh")],
        {"GITHUB_STEP_SUMMARY": "", "STREAM_SUMMARY_FILE": ""},
    )
    assert "$ Bash: ROOT=/x" in stdout


def test_bash_command_body_redacted():
    """A secret in a Bash command must be redacted before it reaches the log
    (the log is world-visible; redaction is the sole guard now bodies are on)."""
    secret = "ghp_" + "A" * 36
    stdout, _ = _run_events(
        [_tool("Bash", command=f'gh api x --header "token={secret}"')],
        {"GITHUB_STEP_SUMMARY": "", "STREAM_SUMMARY_FILE": ""},
    )
    assert secret not in stdout
    assert "REDACTED" in stdout


def test_non_string_command_does_not_crash_pipe():
    """A truthy non-string `command` (list/int, pre tool-schema validation) must
    not raise and kill the stream — the tally and later rendering must survive."""
    stdout, stderr = _run_events(
        [
            _tool("Bash", command=42),
            _tool("Bash", command=["echo", "hi"]),
            _tool("Read", file_path="a.py"),
        ],
        {"GITHUB_STEP_SUMMARY": "", "STREAM_SUMMARY_FILE": ""},
    )
    # pipe survived: the tally (emitted last) is present with all three calls
    assert "🔧 tool calls: Bash 2, Read 1 (total 3)" in stderr


def test_long_command_truncated():
    """Command bodies over ~120 chars are truncated with an ellipsis."""
    long_cmd = "rg " + "x" * 200 + " src/"
    stdout, _ = _run_events(
        [_tool("Bash", command=long_cmd)],
        {"GITHUB_STEP_SUMMARY": "", "STREAM_SUMMARY_FILE": ""},
    )
    line = next(ln for ln in stdout.splitlines() if "$ Bash:" in ln)
    assert line.endswith("...")
    assert len(line) < 140


def test_redactor_load_failure_fails_loud_and_pipe_survives():
    """If redact-secrets.py can't be loaded, _redact degrades to identity — but
    the degrade must be LOUD (stderr warning), not silent, since it's the sole
    guard on the world-visible command log. The pipe must still exit 0."""
    with tempfile.TemporaryDirectory() as d:
        # Copy stream-pretty.py alone — no sibling redact-secrets.py => load fails.
        lone = Path(d) / "stream-pretty.py"
        shutil.copy(SCRIPT, lone)
        r = subprocess.run(
            [sys.executable, str(lone)],
            input=_tool("Bash", command="echo hi"),
            text=True,
            capture_output=True,
            env={**os.environ, "GITHUB_STEP_SUMMARY": "", "STREAM_SUMMARY_FILE": ""},
            check=True,  # must still exit 0
        )
        assert "redact-secrets unavailable" in r.stderr
        assert "UNREDACTED" in r.stderr
        assert "echo hi" in r.stdout  # command still logged (fail-open, not closed)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("all stream-pretty tests passed")
