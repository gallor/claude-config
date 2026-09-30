# claude-config

A **reference snapshot** of my [Claude Code](https://claude.ai/code) setup — the
rules, subagents, and skills I use day to day across our Python / trading-systems
stack. It's here to **browse for ideas**, not to clone and run.

## What's here

| Path | What it is |
|------|------------|
| `CLAUDE.md` | Top-level instructions loaded every session — the index that wires everything together |
| `rules/` | 11 rule files: command-line conventions, Python/pytest style, code-quality workflow, the Claims-vs-Hypotheses evidence discipline, agent triggers, etc. |
| `agents/` | 19 subagent definitions (personas), each pinned to a model and scoped to a domain (perf trio, security, C++, debugging, review, docs, …) |
| `skills/` | 20 slash-command workflows (`/review`, `/tdd`, `/incident`, `/kpop`, `/flume`, language-pro helpers, …) and shared `lib/` scripts |
| `commands/` | Standalone slash commands |
| `scripts/` | Statusline + tmux integration helpers, plus `claude-migrate.sh` (move Claude Code state between machines) |
| `settings.example.json` | The structure of my `settings.json` (model pinning, hooks, plugins, agent-teams flag) with all tokens redacted |

## How to read it

Start with [`CLAUDE.md`](CLAUDE.md) — it's the map. The tables there point at the
rule files, agents, and skills, so you can follow a thread from "when does this
fire" down into the actual prompt.

A few things worth a look if you're skimming:

- **`rules/claims-vs-hypotheses.md`** — the evidence discipline that everything
  else leans on. Label uncertainty as a Hypothesis; promote to a Claim only with
  profiling / benchmark / test evidence.
- **`rules/agent-triggers.md`** — when each subagent auto-fires and how
  specialists escalate into each other.
- **`agents/`** — the personas. Each is a self-contained system prompt.
- **`skills/review/`**, **`skills/tdd/`**, **`skills/kpop/`** — the
  cross-cutting workflows I reach for most.

## If you want to actually adopt a piece

Copy the file(s) into your own `~/.claude/` (e.g. drop an agent into
`~/.claude/agents/`, a rule into `~/.claude/rules/` and reference it from your own
`CLAUDE.md`). Don't clone this over your home config — you'd clobber your own
settings, history, and credentials. Treat it as a parts bin, not a drop-in.

## Not included (deliberately)

- **Secrets / credentials** — `settings.json`, OAuth tokens, anything with a key.
  See `settings.example.json` for the redacted structure.
- **Runtime state** — session transcripts, history, caches, per-project memory.
