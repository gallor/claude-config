---
name: release-check
description: Assess whether origin/main is release-worthy. Checks own unreleased changes, CI status, and (for non-well-known-set repos) dep updates from the well-known set with changelog summaries.
user-invocable: true
argument-hint: [path]
allowed-tools: ["Bash", "Glob", "Grep", "Read"]
---

# Release Check

Determine whether `origin/main` of a repo is release-worthy.

**Repo:** `$ARGUMENTS` if provided, otherwise cwd.

---

## Well-Known Set

These repos are tracked as dependency sources. If the repo being checked IS one of these, skip dep checking entirely.

| Package name | Local path |
|---|---|
| `chippy` | `~/git/chippy` |
| `core-python` | `~/git/core_python` |
| `typemaster` | `~/git/typemaster` |
| `camus-python` | `~/git/camus-python` |
| `camus-ws` | `~/git/camus-ws` (no tags yet — skip) |

---

## Step 1 — Identify the repo

```bash
REPO_PATH="${ARGUMENTS:-$(pwd)}"
cd "$REPO_PATH"
REPO_NAME=$(basename "$REPO_PATH")
```

Determine the package name from `conda-recipe/meta.yaml` (the `name:` field under `package:`), or fall back to `$REPO_NAME`.

---

## Step 2 — Fetch and find last release

```bash
git fetch origin main -q

# Last release version
LAST_RELEASE=$(git log origin/main --oneline --grep="Preparing for v" -1 | grep -oP 'v[\d.]+')
LAST_RELEASE_COMMIT=$(git log origin/main --oneline --grep="Preparing for v" -1 --format="%H")
```

If no release commit found, note "no prior release found" and treat all commits as unreleased.

---

## Step 3 — CI status

```bash
HEAD_SHA=$(git rev-parse origin/main)
source ~/.claude/skills/lib/gh-env.sh
export GH_HOST
```

```bash
gh api "repos/{owner}/{repo}/commits/$HEAD_SHA/check-runs" \
  --jq '.check_runs[] | {name: .name, conclusion: .conclusion}' 2>/dev/null
```

Determine owner/repo from `git remote get-url origin`.

**Classifying failures — chronic vs regression:**

Before marking CI red, check whether each failing check was also failing at the last release commit:

```bash
gh api "repos/{owner}/{repo}/commits/$LAST_RELEASE_COMMIT/check-runs" \
  --jq '[.check_runs[] | select(.conclusion == "failure" or .conclusion == "error") | .name]' 2>/dev/null
```

- If a failing check was **also failing at the last release commit** → chronic failure, not a blocker. Note it as ⚠ pre-existing.
- If a failing check is **new since the last release** → regression, blocks release. Mark CI red.
- If the last release commit has no check-runs (e.g. it predates CI) → treat all failures as potential regressions.

CI is **green** if all non-skipped checks pass, or all failures are chronic (pre-existing at last release).
CI is **red** only if there is at least one failure that was not present at the last release commit.

---

## Step 4 — Own unreleased changes

List newsfragments present on `origin/main` that are not template/boilerplate:

```bash
git ls-tree origin/main newsfragments/ \
  | awk '{print $4}' \
  | grep -vE '(template|changelog|towncrier|README|\+PR\+|\.j2|^newsfragments/$)'
```

For each fragment, read its content:
```bash
git show origin/main:newsfragments/<fragment>
```

Classify each by type from the filename suffix:
- `.feature` / `.feature.md` → Feature
- `.bugfix` / `.bugfix.md` → Bugfix
- `.removal` / `.removal.md` → Breaking removal
- `.deprecated` / `.deprecated.md` → Deprecation
- `.perf` / `.perf.md` → Performance
- `.doc` / `.doc.md` → Docs
- `.misc` / `.misc.md` → Misc

---

## Step 5 — Dep updates (skip if repo is in the well-known set)

Read `conda-recipe/meta.yaml` on `origin/main`. Extract `run:` dependencies and intersect with the well-known set. For each matching dep:

### 5a — Get versions

```bash
# Constraint from meta.yaml (e.g. ">=2026.4.2" → "2026.4.2")
BASELINE=$(grep '<pkg>' conda-recipe/meta.yaml | grep -oP '[\d]+\.[\d.]+' | head -1)

# Latest tag in dep's local repo
git -C ~/git/<local_path> fetch --tags -q 2>/dev/null
LATEST=$(git -C ~/git/<local_path> tag --sort=-creatordate | head -1 | sed 's/^v//')
```

Skip camus-ws (no tags yet).

### 5b — Compare versions

Use Python for reliable version comparison:

```bash
python3 -c "
from packaging.version import Version
print(Version('$LATEST') > Version('$BASELINE'))
"
```

If `LATEST > BASELINE` → dep has updates to report.

### 5c — Extract changelog between versions

**For repos with `CHANGES.md` or `CHANGELOG.md`** (chippy, camus-python, typemaster):

```bash
git -C ~/git/<local_path> show HEAD:CHANGES.md 2>/dev/null \
  || git -C ~/git/<local_path> show HEAD:CHANGELOG.md
```

Extract all sections with version > BASELINE and version <= LATEST. Sections are delimited by lines matching `## <version>`. Read the section content; strip issue links to keep output concise.

**For repos without a CHANGES file** (core-python):

```bash
git -C ~/git/core_python log v$BASELINE..v$LATEST --oneline \
  | grep -v "Preparing for v"
```

---

## Step 6 — Verdict and output

### Release-worthy if:
- CI is green, AND
- At least one of: own unreleased changes exist OR dep updates exist in the well-known set

### Not release-worthy if:
- CI is red (regardless of changes), OR
- No own changes AND no dep updates

### Impact classification

From the union of own changes + dep changelog entries, classify overall impact:

| Label | Criteria |
|---|---|
| **Breaking** | Any removal/deprecation entries |
| **Feature** | Any feature entries (no breaking) |
| **Bugfix** | Only bugfixes / perf / misc |
| **Perf** | Only perf entries |
| **Docs** | Only doc entries |

---

## Output format

```
## <repo-name> — release-worthy ✓  (or ✗)

**Last release:** vX.Y.Z
**CI:** green ✓ (or red ✗ — <failing check name>)
**Impact:** <Breaking | Feature | Bugfix | Perf | Docs>

### Own changes (since vX.Y.Z)
- [Feature] <fragment content>
- [Bugfix] <fragment content>

### Dep updates
- **chippy** v2026.4.2 → v2026.4.3
  - [Bugfix] <changelog entry>
  - [Feature] <changelog entry>
- **core-python** v2026.3.4 → v2026.4.0
  - <commit summary>
  - <commit summary>
```

If no own changes: `**Own changes:** none`
If no dep updates (or repo is in well-known set): omit the dep updates section.
If CI is red (new regression): bold the CI line and state not release-worthy regardless of changes.
If CI has chronic pre-existing failures: `**CI:** green ✓ (⚠ <check-name> failing pre-existing since before vX.Y.Z)`
If a dep's local repo is missing: `- **<pkg>:** local repo not found — skipped`
