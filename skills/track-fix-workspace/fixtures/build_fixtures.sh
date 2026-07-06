#!/usr/bin/env bash
# Builds deterministic scratch git repos + a mock `gh` for each track-fix eval scenario.
# Each fixture is fully self-contained: a git repo with a fake "origin" remote and a
# bin/gh shim on PATH that returns canned JSON. No real GitHub is touched.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export GIT_AUTHOR_NAME="Test" GIT_AUTHOR_EMAIL="test@example.com"
export GIT_COMMITTER_NAME="Test" GIT_COMMITTER_EMAIL="test@example.com"

make_origin() {
  # $1 = fixture dir. Creates a bare repo to act as `origin` and a working clone.
  local dir="$1"
  rm -rf "$dir"
  mkdir -p "$dir"
  git init --bare -q "$dir/origin.git"
  git clone -q "$dir/origin.git" "$dir/repo"
}

write_mock_gh() {
  # $1 = fixture dir, $2 = path to canned-responses json
  local dir="$1" responses="$2"
  mkdir -p "$dir/bin"
  cp "$ROOT/mock_gh.py" "$dir/bin/gh-impl.py"
  cp "$responses" "$dir/bin/gh_responses.json"
  cat > "$dir/bin/gh" <<'EOF'
#!/usr/bin/env bash
exec python3 "$(dirname "$0")/gh-impl.py" "$@"
EOF
  chmod +x "$dir/bin/gh"
}

# ---------- Scenario 0: no ticket, work on main ----------
S0="$ROOT/eval-0"
make_origin "$S0"
(
  cd "$S0/repo"
  git config init.defaultBranch main
  cat > parser.py <<'PY'
def parse(text):
    return text.split(",")
PY
  git add parser.py && git commit -q -m "Initial parser"
  git branch -M main
  git push -q -u origin main
  # The "fix" — uncommitted change on main, no issue anywhere.
  cat > parser.py <<'PY'
def parse(text):
    if not text:
        return []
    return text.split(",")
PY
)
write_mock_gh "$S0" "$ROOT/responses_no_ticket.json"

# ---------- Scenario 1: ticket number in branch name, issue exists, NO PR ----------
S1="$ROOT/eval-1"
make_origin "$S1"
(
  cd "$S1/repo"
  cat > config_loader.py <<'PY'
import json
def load(path):
    with open(path) as f:
        return json.load(f)
PY
  git add config_loader.py && git commit -q -m "Initial config loader"
  git branch -M main
  git push -q -u origin main
  git switch -q -c fix-config-loader-207
  cat > config_loader.py <<'PY'
import json
def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
PY
)
write_mock_gh "$S1" "$ROOT/responses_issue_no_pr.json"

# ---------- Scenario 2: ticket found, issue exists AND has PR attached ----------
S2="$ROOT/eval-2"
make_origin "$S2"
(
  cd "$S2/repo"
  cat > auth.py <<'PY'
def login(user, pw):
    return check(user, pw)
PY
  git add auth.py && git commit -q -m "Initial auth"
  git branch -M main
  git push -q -u origin main
  git switch -q -c bugfix-311
  cat > auth.py <<'PY'
def login(user, pw):
    if not user or not pw:
        raise ValueError("missing credentials")
    return check(user, pw)
PY
)
write_mock_gh "$S2" "$ROOT/responses_issue_with_pr.json"

echo "Fixtures built under $ROOT: eval-0, eval-1, eval-2"
