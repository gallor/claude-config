#!/usr/bin/env python3
"""Pretty-print claude --output-format stream-json for GitHub Actions logs.

Adds emoji per tool type and wraps tool calls in ::group:: / ::endgroup::
so they collapse in the Actions UI, letting the final text output stand out.

Also writes the distilled final summary to two optional sinks, when their
env vars are set:
  - $GITHUB_STEP_SUMMARY — the run's Summary tab (review-bot + calibrate).
  - $STREAM_SUMMARY_FILE — an arbitrary path the caller reads later. The
    calibrate workflow points each calibrator at its own file, then folds
    those into the calibration PR body (a later step can't read another
    step's $GITHUB_STEP_SUMMARY, so a checkout-relative file bridges them).
Both receive the same distilled text; the sink env vars are independent.
"""

import collections
import importlib.util
import json
import os
import re
import sys

# Reuse the deterministic secret redactor as a library — command bodies are logged
# to a world-visible Actions log, so every printed command runs through it first.
# Loaded by path (hyphenated filename isn't a normal import); falls back to identity
# if unavailable so logging never crashes the pipe.
try:
    _spec = importlib.util.spec_from_file_location(
        "redact_secrets", os.path.join(os.path.dirname(__file__), "redact-secrets.py")
    )
    _rs = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_rs)

    def _redact(text):
        redacted, _ = _rs.redact_text(text)
        return redacted
except Exception as e:
    # Fail loud, not silent: redaction is the sole guard on the world-visible
    # command log, so a down guard must be observable in the job log rather than
    # streaming every subsequent Bash command raw with no signal. Mirrors
    # redact-secrets.py's own main(), which warns on pass-through-unredacted.
    print(
        f"stream-pretty: redact-secrets unavailable ({type(e).__name__}: {e}); "
        "Bash command bodies logged UNREDACTED",
        file=sys.stderr,
        flush=True,
    )

    def _redact(text):
        return text


# A pure setup line: one or more `VAR=value` assignments (optionally `export`-ed)
# and nothing else — no trailing command word, no command substitution. These
# open a multi-line Bash body to stage a path/env, so line 1 is not the operative
# call; skip past them to the first real command.
#
# The value part deliberately EXCLUDES command substitution: `(?!\$\()[^\s`]*` is
# a run of non-space, non-backtick chars where no token STARTS a `$(`. So a value
# that runs a subprocess — `NOW=$(date)`, `TMPFILE=$(mktemp)`, `X=`cmd`` — fails
# the pattern and the line is (correctly) treated as OPERATIVE, whether or not the
# substitution contains internal whitespace. What still counts as setup: literal
# paths (`ROOT=/x`), URLs with `?`/`&`/`=` in the value (`URL=http://h?a=1`), and
# plain variable expansion (`VAR=$OTHER`, no subprocess). An env-prefix like
# `TZ=UTC date` fails too — the trailing `date` token is not a `VAR=value`.
_BARE_VALUE = r"(?:(?!\$\()[^\s`])*"
_ASSIGN_ONLY = re.compile(
    rf"^(?:export\s+)?(?:[A-Za-z_][A-Za-z0-9_]*={_BARE_VALUE}\s*)+$"
)

# A pure setup BUILTIN: `source`/`.` (load env into a fresh shell) or `cd` (stage
# a dir), taking exactly one argument and NOTHING else — no chaining operator. Same
# masking class as a bare assignment: each Bash tool call is a fresh shell, so a
# `source ~/.../gh-env.sh` on its own line is inert unless the operative `gh` is on
# the next line (the review skill mandates sourcing gh-env.sh before every `gh`), so
# line 1 hides the real call. A chained form (`cd /x && cat y`, `source e; gh ...`)
# carries its operative work on the SAME line, so excluding `&`/`|`/`;` leaves it
# intact and it is shown in full. The argument ALSO excludes command substitution
# (`(?!\$\()` + no backtick), mirroring `_ASSIGN_ONLY` — `source $(locate_env_file)`
# ran a subprocess, so it is operative, not setup (the same guard, same reason as
# `NOW=$(date)`). Word boundary via the required `\s+` means `cdr`/`sourced`/
# `sourcefile=x` are not matched as this builtin.
_SETUP_CMD = re.compile(r"^(?:source|\.|cd)\s+(?:(?!\$\()[^\s`&|;])+\s*$")

# A WHOLE-LINE assignment whose value RUNS a subprocess: `CTX=$(cat f)`, `NOW=$(date)`,
# `X=`cmd``. Same literal shape as `_ASSIGN_ONLY` except the value is (or contains) a
# command substitution, and the line carries no chaining operator (a chained form like
# `CTX=$(...) && cat "$CTX/x"` already shows its work, so it is a strong operative line
# and must not match here). These are *weak* operative candidates — see `_operative_line`.
_CMDSUB_ASSIGN = re.compile(
    r"^(?:export\s+)?[A-Za-z_][A-Za-z0-9_]*=(?:[^\s`&|;]*(?:\$\([^)]*\)|`[^`]*`)[^\s`&|;]*)\s*$"
)

# An `echo`/`printf` that only DISPLAYS variables/literals — no pipe, no redirect, no
# substitution (neither `$(...)` via the lookahead nor backticks via the char class).
# This is the tell that distinguishes the two `VAR=$(cmd)` + next-line shapes:
# `CID=$(gh api …)` / `echo $CID` means line 1 did the work and line 2 just prints it
# (keep line 1); `CTX=$(cat /tmp/state)` / `cat "$CTX/diff.patch"` means line 1 was a
# prologue and line 2 is the work (keep line 2). The `(?!.*\$\()` guard matters: an
# `echo $(ls "$CTX")` RUNS a subprocess, so it is real work and must not be treated as
# display-only — without it a weak prologue would shadow it, the exact bug this file
# fixes one level deeper. Bare `$`/`(` stay allowed (`echo $CID`, `echo (note)`).
# Only consulted when a weak cmd-sub assignment already matched, so a bare
# `echo "=== hdr ==="` opening an ordinary body is still operative and shown as before.
_ECHO_ONLY = re.compile(r"^(?!.*\$\()(?:echo|printf)\s+[^`|>;&]*$")


def _operative_line(cmd):
    """First non-blank, non-setup line of a command body (the one that shows WHAT
    ran). Setup = a bare `VAR=value` assignment or a `source`/`.`/`cd` builtin
    staging env/dir for the operative line that follows. Falls back to the first
    non-blank line if every line is setup, and to "" for an all-blank/empty body.

    A command-substitution assignment (`CTX=$(cat f)`, `NOW=$(date)`) is a *weak*
    candidate: it ran a subprocess, so it beats pure setup and is shown when it is
    all the call does — but it must NOT shadow real work on a later line. The
    prologue `CTX=$(cat /tmp/ctx)\\ncat "$CTX/diff.patch"` is the common shape in a
    kaa review body; returning line 1 there hid every such call behind an identical
    variable re-read (observed 6x in camus-ws run 7764082, each carrying 12-60s of
    think-time, which read as narration waste when it was real work). So: scan on,
    and only fall back to the weak candidate if no strong line exists."""
    first_nonblank = ""
    weak = ""
    for raw in cmd.splitlines():
        line = raw.strip()
        if not line:
            continue
        if not first_nonblank:
            first_nonblank = line
        if _SETUP_CMD.match(line) or _ASSIGN_ONLY.match(line):
            continue  # pure setup: staged env/dir/literal, never operative
        if _CMDSUB_ASSIGN.match(line):
            # Ran a subprocess, but may be a prologue — keep looking. Track the LAST
            # such line, not the first: with two stacked assignments
            # (`CTX=$(cat f)` then `RESULT=$(grep -c p "$CTX/f")`) the terminal one is
            # the work and the opener is the prologue, mirroring how a later strong
            # line already wins over an earlier weak one.
            weak = line
            continue
        if weak and _ECHO_ONLY.match(line):
            continue  # `echo $CID` after `CID=$(gh api …)`: the assignment WAS the work
        return line  # a real command
    return weak or first_nonblank


EMOJI = {
    "Bash": "$",
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
summary_chunks = []  # accumulate text for GITHUB_STEP_SUMMARY
tool_counts = collections.Counter()  # per-tool call tally (orchestrator-scoped)


def ensure_newline():
    global at_line_start
    if not at_line_start:
        print(flush=True)
        at_line_start = True


def open_group():
    global in_group
    if not in_group:
        ensure_newline()
        print("::group::🛠️ Tool calls", flush=True)
        in_group = True


def close_group():
    global in_group
    if in_group:
        ensure_newline()
        print("::endgroup::", flush=True)
        in_group = False


for line in sys.stdin:
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
            tool_counts[name] += 1
            open_group()
            # For Bash, log the (redacted) first OPERATIVE line so a slow review's
            # call pattern is auditable after the fact — the count says HOW MANY,
            # the bodies say WHETHER they were batchable. A body that opens with a
            # bare `ROOT=/path` setup assignment would otherwise log only that
            # (hiding the grep/cat/gh on line 2+), defeating the batchability
            # signal — so skip pure-assignment lines. Redact first: this log is
            # world-visible. Other tools stay name-only (inputs are noisier, not
            # the round-trip-cost signal).
            if name == "Bash":
                cmd = (block.get("input") or {}).get("command", "")
                # `command` is whatever the model emitted; a truthy non-string
                # (list/int, pre tool-schema validation) would make redact_text's
                # .subn() raise and kill the pipe — coerce so the log survives.
                if not isinstance(cmd, str):
                    cmd = str(cmd)
                first = _operative_line(_redact(cmd)) if cmd else ""
                if len(first) > 120:
                    first = first[:117] + "..."
                print(
                    f"  {emoji} {name}: {first}" if first else f"  {emoji} {name}",
                    flush=True,
                )
            else:
                print(f"  {emoji} {name}", flush=True)
            at_line_start = True
        elif btype == "text":
            text = block.get("text", "")
            if text.strip():
                close_group()
                print(text, end="", flush=True)
                at_line_start = text.endswith("\n")
                summary_chunks.append(text if text.endswith("\n") else text + "\n")

close_group()

# Distil the final summary and write it to any configured sink.
# The summary is an anchored heading block onward; everything before it is
# intermediate narration. If nothing matches, fall back to full text.
#
# Two extraction modes, chosen by whether $STREAM_SUMMARY_FILE is set, so the
# review-bot path is provably unchanged:
#   - review-bot ($STREAM_SUMMARY_FILE unset): the original narrow, FIRST-match
#     anchor on "## 🔴/🟡/🟢 Review: ..." — byte-identical to prior behavior.
#   - calibrate ($STREAM_SUMMARY_FILE set): also match calibrator headers
#     (Calibration / Lessons Calibration / Per-flavor / calibrate-*), and take
#     the LAST match — a calibrator emits an earlier "**...complete.**" block
#     before the real summary table, so the final anchored heading is the one.
# Broadening + last-match are gated on the calibrate path precisely because a
# review body can legitimately quote a second matching heading after its verdict
# (e.g. a PR discussing calibrate output) — last-match there would grab the
# wrong block. The review-bot path never opts into either change.
if summary_chunks:
    import re

    full_text = "".join(summary_chunks)
    if os.environ.get("STREAM_SUMMARY_FILE"):
        anchor = re.compile(
            r"(^|\n)(## [🔴🟡🟢].+"
            r"|#{2,3} [`*]*(?:Calibration|Lessons Calibration|Per-flavor|calibrate-).*)"
        )
        matches = list(anchor.finditer(full_text))
        summary_text = full_text[matches[-1].start(2) :] if matches else full_text
    else:
        match = re.search(r"(^|\n)(## [🔴🟡🟢].+)", full_text)
        summary_text = full_text[match.start(2) :] if match else full_text

    # $GITHUB_STEP_SUMMARY — the run's Summary tab (append; step-scoped).
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a") as f:
            f.write(summary_text)

    # $STREAM_SUMMARY_FILE — caller-owned path (overwrite; one summary per run).
    stream_file = os.environ.get("STREAM_SUMMARY_FILE")
    if stream_file:
        with open(stream_file, "w") as f:
            f.write(summary_text)

# Tool-call tally — ALWAYS emitted (every review, no gate), AFTER the summary so it
# reads as a footer below the verdict. Orchestrator-scoped: this pipe sees only the
# top-level agent's tool_use blocks, not aspect subagents' internal calls (separate
# contexts). That is the signal we want — a 347-call blowup is the orchestrator
# serializing its own checks (the batchable #96/#97 surface). To the Actions Summary
# tab so a slow review is visible without pulling job logs; slowness is only known
# post-hoc, so the count must be present on every run. Only $GITHUB_STEP_SUMMARY (not
# $STREAM_SUMMARY_FILE — that is the calibrate PR-body handoff, which must stay the
# distilled summary alone).
if tool_counts:
    total = sum(tool_counts.values())
    parts = ", ".join(f"{n} {c}" for n, c in tool_counts.most_common())
    tally_line = f"\n🔧 tool calls: {parts} (total {total})\n"
    _step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if _step_summary:
        with open(_step_summary, "a") as f:
            f.write(tally_line)
    # Also to stderr so it lands in the raw job log even with no Summary sink set
    # (interactive/local runs), without polluting stdout's rendered stream.
    print(tally_line.strip(), file=sys.stderr, flush=True)
