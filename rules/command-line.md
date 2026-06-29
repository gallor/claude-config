# Command Line Conventions

- Use `rg` for terminal searches. For compressed files (`.zst`, `.gz`, etc.), use `rg -z` — it parallelizes decompression across files internally, making it ~2x faster than `zstd -dc | rg` on 2+ files and dramatically faster at scale. Single-file performance is comparable either way.
- Use `gh` for GitHub interactions (PRs, issues, repos, etc.). See `rules/github-issues.md` for issue creation conventions and the `/sub-issue` skill.
- When the user provides a `git.drwholdings.com` link, always use `gh` to access that information (PRs, issues, etc.).
- Use `jq` for JSON processing.
- Use `yq` for YAML processing
- Use `bat` for file viewing/paging.

## Version Specifiers

- Version strings matching the pattern `YYYY.MM.DDsolveN` (e.g., `2026.02.23solve1`) are `conservationist-cli` environment definitions. Use the `/conservationist` skill for related tasks.

## Local Environment

- Local git repositories are stored in `~/code/`.
