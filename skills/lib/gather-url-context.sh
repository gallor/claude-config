#!/usr/bin/env bash
# Extract + allowlist-triage URLs found in a PR body/comments for review context (kaa#32).
# Usage:
#   gather-url-context.sh --extract <text-file> [--out <dir>] [--allowlist <file>]
#   gather-url-context.sh <url> [<url> ...] [--out <dir>] [--allowlist <file>]
#
# --extract reads a file (PR body + comments), pulls out http(s) URLs, DROPS the
# already-covered/noise classes (GitHub issue/PR links, images/badges, CI/api
# noise), then triages the remainder.
#
# SECURITY MODEL — SSRF closed by construction (claude-config#94):
# The canonical statement of the model and the entry criteria lives in the
# allowlist header (skills/review/url-allowlist.txt) — do not restate it here.
# This script is its enforcement: `readable:true` ONLY if https, default port,
# and the host of the origin AND every redirect hop is on the allowlist. It is a
# cheap curl-only reachability check (no content read); the review skill
# WebFetches only the readable ones and treats fetched bytes as untrusted data
# (see SKILL.md).

set -euo pipefail

OUT=""
EXTRACT_FILE=""
ALLOWLIST="${HOME}/.claude/skills/review/url-allowlist.txt"
URLS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT="$2"; shift 2 ;;
    --extract) EXTRACT_FILE="$2"; shift 2 ;;
    --allowlist) ALLOWLIST="$2"; shift 2 ;;
    *) URLS+=("$1"); shift ;;
  esac
done
OUT="${OUT:-$(mktemp -d /tmp/url-ctx-XXXXXX)}"
mkdir -p "$OUT"

MAX_TRIAGE=20   # hard cap on URLs curled — bound fan-out from a link-heavy PR/comment thread

if [ -n "$EXTRACT_FILE" ] && [ -f "$EXTRACT_FILE" ]; then
  mapfile -t URLS < <(
    grep -oiE 'https?://[a-z0-9._~:/?#@!$&()*+,;=%-]+' "$EXTRACT_FILE" 2>/dev/null \
      | sed -E 's#[).,;:!"'"'"'>]+$##' \
      | sort -u \
      | grep -viE '/(issues|pull)/[0-9]+' \
      | grep -viE '(user-images|avatars|/badge|shields\.io|\.(png|jpg|jpeg|gif|svg|webp)([?#]|$))' \
      | grep -viE '/(actions/runs|api)/' \
      | head -n "$MAX_TRIAGE" \
      || true
  )
fi

if [ "${#URLS[@]}" -eq 0 ]; then
  echo '[]' > "$OUT/urls.json"
  echo "$OUT"
  exit 0
fi

# host_allowed <host> : true if host is on the allowlist (exact, or dot-suffix for ".domain").
host_allowed() {
  local host; host="$(printf '%s' "$1" | tr 'A-Z' 'a-z')"
  [ -f "$ALLOWLIST" ] || return 1
  local entry
  while IFS= read -r entry; do
    entry="${entry%%#*}"; entry="$(printf '%s' "$entry" | tr -d '[:space:]' | tr 'A-Z' 'a-z')"
    [ -n "$entry" ] || continue
    if [ "${entry#.}" != "$entry" ]; then
      # ".domain" → match domain itself or any subdomain, on a dot boundary
      local dom="${entry#.}"
      [ "$host" = "$dom" ] && return 0
      case "$host" in *".$dom") return 0 ;; esac
    else
      [ "$host" = "$entry" ] && return 0
    fi
  done < "$ALLOWLIST"
  return 1
}

# parse_authority <https-url> : echo "<host> <port>" for a safe authority, or return 1.
# Rejects any authority containing userinfo (@) outright — a URL like
# https://github.com:x@169.254.169.254/ would otherwise split on the first ':'
# and validate the userinfo ("github.com") while curl connects to the real host
# (169.254.169.254). userinfo has no legitimate use for fetching a doc, so we
# refuse it rather than parse around it. (claude-config#94, userinfo SSRF vector.)
parse_authority() {
  local url="$1" authority host port
  authority="${url#https://}"; authority="${authority%%/*}"
  case "$authority" in *@*) return 1 ;; esac   # no userinfo, ever
  host="${authority%%:*}"; port="${authority##*:}"; [ "$port" = "$authority" ] && port="443"
  # a bracketed IPv6 authority would also break %%:* parsing; reject those too (not needed here)
  case "$host" in *"["*|*"]"*) return 1 ;; esac
  [ -n "$host" ] || return 1
  printf '%s %s\n' "$host" "$port"
}

emit() {  # url final_url status readable reason
  python3 - "$@" <<'PY'
import json, sys
u, final, status, readable, reason = sys.argv[1:6]
print(json.dumps({"url": u, "final_url": final, "status": int(status),
                  "readable": readable == "true", "reason": reason}))
PY
}

RESULTS=()
for u in "${URLS[@]}"; do
  readable="false"; reason=""; status="0"; final="$u"
  # http -> https (mirror WebFetch); reject any non-http(s) scheme outright.
  probe="${u/#http:\/\//https://}"
  case "$probe" in
    https://*) : ;;
    *) reason="rejected scheme (only https)"; RESULTS+=("$(emit "$u" "$probe" 0 false "$reason")"); continue ;;
  esac
  # Extract host+port safely (rejects userinfo/@ and bracketed IPv6 — see parse_authority).
  if ! read -r host port < <(parse_authority "$probe"); then
    reason="rejected authority (userinfo/@ or malformed)"; RESULTS+=("$(emit "$u" "$probe" 0 false "$reason")"); continue
  fi
  if [ "$port" != "443" ]; then
    reason="rejected non-default port ($port)"; RESULTS+=("$(emit "$u" "$probe" 0 false "$reason")"); continue
  fi
  if ! host_allowed "$host"; then
    reason="host not on allowlist ($host)"; RESULTS+=("$(emit "$u" "$probe" 0 false "$reason")"); continue
  fi
  # Follow redirects MANUALLY so every hop's host is re-checked against the allowlist
  # (a redirect to an off-list host — the SSRF vector — is rejected mid-chain).
  cur="$probe"; ok="true"
  for _hop in 1 2 3 4 5; do
    probe_out="$(curl -sS --max-time 15 -o /dev/null \
      -w '%{http_code} %{redirect_url}' "$cur" 2>/dev/null)" || true
    [ -n "$probe_out" ] || probe_out="000 "
    status="${probe_out%% *}"; loc="${probe_out#* }"
    if [ "$status" = "000" ]; then ok="false"; reason="unreachable (dns/timeout/tls)"; break; fi
    if [ -z "$loc" ] || [ "$loc" = "$probe_out" ]; then
      # no redirect → this is the final response
      final="$cur"; break
    fi
    # a redirect: validate the hop target's scheme+authority+port+host before following
    case "$loc" in https://*) : ;; *) ok="false"; reason="redirect to non-https ($loc)"; break ;; esac
    if ! read -r lhost lport < <(parse_authority "$loc"); then ok="false"; reason="redirect to rejected authority (userinfo/@ or malformed: $loc)"; final="$loc"; break; fi
    if [ "$lport" != "443" ]; then ok="false"; reason="redirect to non-default port ($lport)"; break; fi
    if ! host_allowed "$lhost"; then ok="false"; reason="redirect to off-allowlist host ($lhost)"; final="$loc"; break; fi
    cur="$loc"; final="$loc"
  done
  if [ "$ok" = "true" ]; then
    if [ "$status" -ge 200 ] && [ "$status" -lt 300 ]; then
      readable="true"; reason="ok"
    else
      reason="non-2xx ($status)"
    fi
  fi
  RESULTS+=("$(emit "$u" "$final" "$status" "$readable" "$reason")")
done

printf '%s\n' "${RESULTS[@]}" | python3 -c 'import sys,json; print(json.dumps([json.loads(l) for l in sys.stdin if l.strip()]))' > "$OUT/urls.json"
echo "$OUT"
