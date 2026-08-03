#!/usr/bin/env python3
"""Redact secret-shaped values from review text before it is posted.

The review runs with the bot's full (team-equivalent) read scope, but the text
it posts is world-visible on the PR. A search or file read during review can pull
a credential from a private repo into a comment body. This pass masks secret-shaped
spans, deterministically, right before `gh api` / `gh pr comment`.

Usage:
    redact-secrets.py <payload.json>   # JSON payload: rewrite the file in place
    redact-secrets.py -                # raw text on stdin -> redacted text on stdout
    redact-secrets.py --selftest       # run built-in fixtures; exit 1 on any failure

`<file>` mode is for the reviews-API payload (`/tmp/review-body.json`); `-` mode is
for the `gh pr comment` fallback, which pipes a raw markdown body (NOT JSON).

Exit status is always 0 for the two redaction modes (redaction must never be the
reason a post is aborted) — errors are logged to stderr and the input passes
through unchanged. `--selftest` is the exception: it exits non-zero on failure so
CI can guard the regexes against future edits.

Design:
- High-precision provider token prefixes and private-key blocks are masked wherever
  they appear.
- Generic high-entropy values are masked ONLY when assigned to a secret-ish key
  (token=..., password: "..."). Bare high-entropy strings are left alone so that
  legitimate review content (git SHAs, chippy type hashes like 0x8B35DCE7DAA0E4FF,
  base64 snippets under discussion) is not mangled.
- Patterns are derived from the public gitleaks ruleset.
"""

import json
import re
import sys

# --- High-precision patterns: mask the matched span wherever it occurs. ---

_TOKEN_PREFIXES = re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b")
_GH_FINE_PAT = re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b")
_AWS_KEY = re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA)[A-Z0-9]{16}\b")
_GCP_KEY = re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")
_SLACK = re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")
_GITLAB_PAT = re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}\b")
# OpenAI / Anthropic: sk-, sk-proj-, sk-svcacct-, sk-ant-api03-, ... (internal hyphens allowed).
_OPENAI = re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9_\-]{19,}\b")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")
# HTTP "Authorization: Bearer <token>" scheme — space-separated, not key=value,
# so it slips past _ASSIGNED_QUOTED/_ASSIGNED_BARE. Case-insensitive (RFC 6750
# says "Bearer" but curl/gh/clients often send lowercase). Token charset covers
# base64url, JWT segments, hex, and provider-prefixed opaque tokens (sk_live_...).
# The 16-char floor keeps ordinary prose ("Bearer of good news", "Bearer
# authentication") from matching — no real bearer token is that short, and a
# 16+ char single run following the literal word "Bearer" is credential material.
_BEARER_TOKEN = re.compile(r"\b(Bearer)\s+([A-Za-z0-9_\-.=+/]{16,})\b", re.IGNORECASE)
_PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"
    r".*?"
    r"-----END (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----",
    re.DOTALL,
)
# Connection string with embedded credentials: proto://[user]:password@host
# - username optional (`//:pw@host`, common for Redis/Mongo in containers)
# - password matched greedily up to the FINAL '@' before the host, so a password
#   containing '@' is fully masked rather than leaking its tail.
_CONN_STRING = re.compile(
    r"\b([a-zA-Z][a-zA-Z0-9+.\-]*://[^\s:/@]*:)([^\s/]+)(@[^\s:/@]+)"
)

# --- Contextual pattern: value assigned to a secret-ish key. ---
# Two branches so punctuation-heavy passwords don't fail open when explicitly keyed:
#   quoted   -> capture everything between the quotes (any chars, incl. @!#$%)
#   unquoted -> a run of non-space, non-quote chars
_SECRET_KEY = (
    r"\b(?:pass(?:word|wd)?|secret|token|api[_-]?key|access[_-]?key"
    r"|client[_-]?secret|auth[_-]?token|bearer)\b"
)
_ASSIGNED_QUOTED = re.compile(
    rf"(?P<key>{_SECRET_KEY}\s*[:=]\s*)(?P<q>['\"])(?P<val>[^'\"]{{4,}})(?P=q)",
    re.IGNORECASE,
)
_ASSIGNED_BARE = re.compile(
    rf"(?P<key>{_SECRET_KEY}\s*[:=]\s*)(?P<val>[^\s'\"]{{8,}})",
    re.IGNORECASE,
)


def _mask(secret: str) -> str:
    """Reveal a small, length-scaled prefix/suffix for identifiability; mask the rest.

    Short values reveal proportionally less (a fixed 4+4 window exposes most of a
    short secret), so the reveal shrinks to 2+2 under 16 chars and nothing at all
    for very short values.
    """
    n = len(secret)
    if n <= 6:
        return "[REDACTED]"
    keep = 2 if n < 16 else 4
    return f"{secret[:keep]}…{secret[-keep:]} [REDACTED]"


def redact_text(text):
    """Return (redacted_text, count) for a single string.

    `count` comes solely from each subn's returned match count, so a value is
    tallied exactly once.
    """
    count = 0

    text, n = _PRIVATE_KEY_BLOCK.subn("[REDACTED PRIVATE KEY]", text)
    count += n

    for pat in (
        _TOKEN_PREFIXES, _GH_FINE_PAT, _AWS_KEY, _GCP_KEY,
        _SLACK, _GITLAB_PAT, _OPENAI, _JWT,
    ):
        text, n = pat.subn(lambda m: _mask(m.group(0)), text)
        count += n

    text, n = _BEARER_TOKEN.subn(lambda m: f"{m.group(1)} {_mask(m.group(2))}", text)
    count += n

    text, n = _CONN_STRING.subn(
        lambda m: f"{m.group(1)}[REDACTED]{m.group(3)}", text
    )
    count += n

    text, n = _ASSIGNED_QUOTED.subn(
        lambda m: f"{m.group('key')}{m.group('q')}{_mask(m.group('val'))}{m.group('q')}",
        text,
    )
    count += n

    text, n = _ASSIGNED_BARE.subn(
        lambda m: f"{m.group('key')}{_mask(m.group('val'))}", text
    )
    count += n

    return text, count


def redact_obj(obj):
    """Recursively redact every string in a JSON-like structure.

    Walking all strings (not just named body fields) is fail-closed: a secret
    cannot hide in a field we forgot to enumerate. Non-text fields (paths, line
    numbers, event names) don't match the secret patterns, so they pass through.
    """
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, dict):
        out, total = {}, 0
        for k, v in obj.items():
            out[k], n = redact_obj(v)
            total += n
        return out, total
    if isinstance(obj, list):
        out, total = [], 0
        for item in obj:
            r, n = redact_obj(item)
            out.append(r)
            total += n
        return out, total
    return obj, 0


# --- Built-in fixtures (must stay in sync with the regexes above). ---
_MUST_MASK = [
    "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    "AKIAIOSFODNN7EXAMPLE",
    'password = "hunter2secretpw"',
    'password = "P@ssw0rd!123"',                       # punctuation, explicitly keyed
    "api_key: sk-abcdefghijklmnopqrstuvwxyz123456",    # legacy sk-
    "sk-proj-abcdefghijklmnopqrstuvwxyz1234",          # modern OpenAI
    "sk-ant-api03-abcdefghijklmnopqrstuvwxyzABCD",      # Anthropic
    "postgres://user:p@ssw0rd@host:5432/db",           # '@' in password
    "redis://:secretpw@cache:6379",                    # userless DSN
    'curl -H "Authorization: Bearer sk_live_abcdef1234567890opaque" https://x',
    "Authorization: bearer eyJhbGciOiJIUzI1NiJ9.abcdefg.hijklmno",  # lowercase scheme
    "-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n-----END RSA PRIVATE KEY-----",
]
_MUST_KEEP = [
    "chippy type hash 0x8B35DCE7DAA0E4FF resolves to WorldTradeFeed",
    "commit a462e59049c226a06f3d1e9c8b7a5 fixes this",
    "use flpc.findall(compiled, text) for bulk matching",
    "the variable token_count tracks how many tokens were seen",
]


def _selftest():
    failures = []
    for s in _MUST_MASK:
        out, n = redact_text(s)
        # The leaked-tail case: assert no plaintext password fragment survives.
        if n == 0 or out == s:
            failures.append(f"NOT MASKED: {s!r} -> {out!r}")
        elif "ssw0rd@host" in out:
            failures.append(f"PARTIAL LEAK: {s!r} -> {out!r}")
    for s in _MUST_KEEP:
        out, n = redact_text(s)
        if out != s:
            failures.append(f"WRONGLY ALTERED: {s!r} -> {out!r}")
    if failures:
        print("redact-secrets --selftest FAILED:", file=sys.stderr)
        for f in failures:
            print("  " + f, file=sys.stderr)
        return 1
    print(
        f"redact-secrets --selftest OK "
        f"({len(_MUST_MASK)} masked, {len(_MUST_KEEP)} preserved).",
        file=sys.stderr,
    )
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        sys.exit(1)

    arg = sys.argv[1]

    if arg == "--selftest":
        sys.exit(_selftest())

    # Redaction modes: never let an error here abort the post. Log and pass through.
    count = 0
    try:
        if arg == "-":
            redacted, count = redact_text(sys.stdin.read())
            sys.stdout.write(redacted)
        else:
            with open(arg) as f:
                payload = json.load(f)
            redacted, count = redact_obj(payload)
            with open(arg, "w") as f:
                json.dump(redacted, f)
    except Exception as e:  # noqa: BLE001 - deliberate catch-all; must not block posting
        print(
            f"redact-secrets: passed through unredacted ({type(e).__name__}: {e}).",
            file=sys.stderr,
        )
        sys.exit(0)

    if count:
        print(
            f"redact-secrets: masked {count} secret-shaped value(s) before posting.",
            file=sys.stderr,
        )
    sys.exit(0)


if __name__ == "__main__":
    main()
