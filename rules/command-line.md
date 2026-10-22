# Command Line Conventions

- Use `rg` for terminal searches. For compressed files (`.zst`, `.gz`, etc.), use `rg -z` — it parallelizes decompression across files internally, making it ~2x faster than `zstd -dc | rg` on 2+ files and dramatically faster at scale. Single-file performance is comparable either way.
- **Prefer the `git-rw` MCP server for all GitHub interactions** (PRs, issues, reviews, comments, repos, branches, files, releases, tags, search). Reach for the `mcp__git-rw__*` tools first; fall back to the `gh` CLI only when the MCP server is unavailable (its tools aren't listed for the session) or a needed operation has no MCP equivalent. See `rules/github-issues.md` for issue conventions and the `/sub-issue` skill.
- When the user provides a `git.drwholdings.com` link, access it via the `git-rw` MCP tools (e.g. `pull_request_read`, `issue_read`), falling back to `gh` if the MCP server is unavailable.
- Editing a PR (title, body, reviewers, base, draft, state) goes through `mcp__git-rw__update_pull_request`, which works correctly in our GHE environment (no GraphQL-mutation workaround needed).
- **Only when falling back to `gh`: never use `gh pr edit`** — it issues a GraphQL mutation that fails in our GHE environment. Use the REST API (`gh api`) instead. Map the `gh pr edit` flag to its REST endpoint (owner/repo from `gh repo view --json nameWithOwner --jq .nameWithOwner`; keep `GH_HOST` exported for GHE):

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

## Git Worktrees — only edit your own

- **Only edit the worktree that is the session's present working directory.** Never make file edits, and never run git mutations (`commit`, `mv`, `rm`, `push`, `add`), in a *different* git worktree — even one reachable by absolute path or `git -C`. Another Claude session is often attached to that worktree; mutating it races with that session and can commit its in-progress work or clobber its state.
- **To change another worktree, message its agent.** Identify the session attached to it with `ListAgents`, then ask that session (via `SendMessage`) to make the change — it owns that working directory and should make the edit itself.
- **If no session is attached to that worktree**, do not edit it silently. Tell the user there is no agent on that worktree and ask whether they still want the change made (and how — e.g. you switch into it, or they start a session there).
- **Reading** another worktree for context is fine; **mutating** it is not.
