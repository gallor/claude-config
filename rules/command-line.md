# Command Line Conventions

- Use `rg` for terminal searches. For compressed files (`.zst`, `.gz`, etc.), use `rg -z` — it parallelizes decompression across files internally, making it ~2x faster than `zstd -dc | rg` on 2+ files and dramatically faster at scale. Single-file performance is comparable either way.
- Use `gh` for GitHub interactions (PRs, issues, repos, etc.). See `rules/github-issues.md` for issue creation conventions and the `/sub-issue` skill.
- When the user provides a `git.drwholdings.com` link, always use `gh` to access that information (PRs, issues, etc.).
- **Never use `gh pr edit`** — it issues a GraphQL mutation that fails in our GHE environment. Use the REST API (`gh api`) instead. Map the `gh pr edit` flag to its REST endpoint (owner/repo from `gh repo view --json nameWithOwner --jq .nameWithOwner`; keep `GH_HOST` exported for GHE):

  | `gh pr edit` flag | REST replacement |
  |-------------------|------------------|
  | `--add-reviewer USER` | `gh api "repos/{owner}/{repo}/pulls/{number}/requested_reviewers" -f "reviewers[]=USER"` |
  | `--title` / `--body` | `gh api "repos/{owner}/{repo}/pulls/{number}" -X PATCH -f title=... -f body=...` |
  | `--add-label` / `--remove-label` | `gh api "repos/{owner}/{repo}/issues/{number}/labels" -f "labels[]=NAME"` (POST adds; `-X DELETE .../labels/NAME` removes) |
  | `--milestone` / `--add-assignee` | `gh api "repos/{owner}/{repo}/issues/{number}" -X PATCH -f milestone=... ` / `-f "assignees[]=USER"` |

  `gh pr view`, `gh pr diff`, `gh pr create`, `gh pr comment`, and `gh pr list` are unaffected — only `gh pr edit` hits the broken mutation.
- Use `jq` for JSON processing.
- Use `yq` for YAML processing
- Use `bat` for file viewing/paging.

## Version Specifiers

- Version strings matching the pattern `YYYY.MM.DDsolveN` (e.g., `2026.02.23solve1`) are `conservationist-cli` environment definitions. Use the `/conservationist` skill for related tasks.

## Local Environment

- Local git repositories are stored in `~/code/`.
