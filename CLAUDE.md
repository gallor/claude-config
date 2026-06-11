# User Rules

## Quick Reference

| Rule File | Purpose | Loaded |
|-----------|---------|--------|
| `rules/command-line.md` | CLI tools (rg, gh, jq, bat) | Always |
| `rules/python.md` | Python/pytest conventions | Always |
| `rules/code-quality.md` | Implementation workflow | Always |
| `rules/agent-triggers.md` | Agent invocation, escalation triggers, model selection | Always |
| `rules/claims-vs-hypotheses.md` | Evidence requirements for claims | Always |
| `rules/agent-teams.md` | Team protocols, chaining, escalation paths | By team skills |
| `rules/github-issues.md` | GH issue creation, labels, sub-issues | By `@technical-doc-writer`, `/sub-issue` |
| `rules/comment-style.md` | Theme-first + collapsible format for posted PR/issue comments | By `/review`, `/pr-pipeline`, `@code-reviewer` |
| `rules/zensical.md` | Zensical config, syntax, conventions | By `@technical-doc-writer` |
| `rules/session-wrapup.md` | Review & suggest CLAUDE.md updates | By `/lessons-learned` |
| `rules/execution-efficiency.md` | Verify before executing; agent vs direct | By agents as needed |

## Available Subagents

| Agent | Model | Use For |
|-------|-------|---------|
| **OPUS (Deep Reasoning)** |
| `@ultrathink-debugger` | opus | Complex bugs, root cause analysis (Claims vs Hypotheses) |
| `@solution-architect` | opus | System design, API design, architectural decisions |
| `@performance-usain-bolt` | opus | Deep optimization, benchmarking, library evaluation |
| `@migration-specialist` | opus | Library migrations, breaking changes, version upgrades |
| `@observability-strategist` | opus | Metrics strategy, SLIs/SLOs, what to measure and why |
| `@incident-analyst` | opus | Post-mortems, root cause analysis, incident patterns |
| `@karen` | opus | Reality-check on claimed task completion (functional validation + spec compliance) |
| `@code-quality-pragmatist` | opus | Review for over-engineering |
| **SONNET (Standard Work)** |
| `@technical-doc-writer` | sonnet | API docs, tutorials, Zensical/MkDocs, newsfragments |
| `@code-craftsman` | sonnet | Feature implementation, refactoring |
| `@security-sentinel` | sonnet | Security review, vulnerability detection, secrets scanning |
| `@performance-college-sprinter` | sonnet | Quick perf review, anti-pattern detection |
| `@performance-benchmark-monkey` | sonnet | Rigorous benchmarks, comparative measurement, regression detection |
| `@observability-sentinel` | sonnet | Telemetry implementation, @telemetrize, Torta queries |
| `@code-reviewer` | sonnet | PR reviews, concise actionable feedback |
| `@cpp-joe` | sonnet | C++-specialized review: ABI/wire compat, register/cache discipline, API hygiene, const-correctness, rollout pacing |
| `@requirements-architect` | sonnet | Requirements gathering, stakeholder communication |
| `@qa-sentinel` | sonnet | Test strategy, test implementation |
| `@tech-debt-tracker` | sonnet | Identify and prioritize technical debt |

## Agent Team Workflows

> Requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` in `settings.json`. Falls back to sequential subagents if disabled.

| Team | Core Roster | Trigger | Details |
|------|-------------|---------|---------|
| **PR Pipeline** | `@code-reviewer`, `@technical-doc-writer` | PR creation | `/pr-pipeline` skill |
| **TDD Feature Dev** | `@qa-sentinel`, `@code-craftsman` | Feature or bug fix (test-first) | `/tdd` skill |
| **Incident Response** | `@ultrathink-debugger` (×N), `@observability-sentinel` | Production incident (Mode A: directed, Mode B: competing hypotheses) | `/incident` skill |

Specialists (`@performance-*`, `@security-sentinel`, `@observability-*`, `@solution-architect`) are spawned dynamically into active teams based on escalation triggers. See `rules/agent-triggers.md#dynamic-escalation-within-teams`.

### Team Skills (Slash Commands)

| Skill | Invocation | Team Spawned |
|-------|------------|--------------|
| `/review` | `/review [aspects]` | Solo or parallel review agents (code, tests, simplify, security, perf) |
| `/pr-pipeline` | `/pr-pipeline` | PR Pipeline Team |
| `/tdd` | `/tdd <description>` | TDD Feature Dev Team |
| `/incident` | `/incident <symptoms>` | Incident Response Team (auto-selects Mode A or B) |
| `/who-needs-me-for-pr` | `/who-needs-me-for-pr [since:<period>] [--all]` | Outstanding PR review requests, sorted by last ping |
| `/flume` | `/flume [--service <name>] <logfiles>` | Run Core log analyzer or add a new metric |
| `/memleak` | `/memleak <PID> [host]` or `/memleak analyze <snapshots>` | Diagnose memory leaks and GC stalls on running CPython processes |

### Log Analysis (flume)

**Trigger `flume` automatically** when a message references `.log` files and asks for analysis, metrics, performance, or comparison. Examples:
- "analyze this log" / "look at these logs" / "what does `<file>.log` show"
- "performance in `<service>` logs" / "compare `<solve1>` vs `<solve2>` logs"
- Any path ending in `.log` combined with analysis intent

**Workflow:**
1. Run `flume <logfiles>` first — output covers startup, latency, errors, request types, heartbeats
2. If a needed metric is missing from flume's output, do ad-hoc `rg` + Python for that metric
3. If the ad-hoc metric would be useful to repeat, note it as a candidate for `/flume <add new metric>`

**Binary**: `~/.local/bin/flume` — auto-detects queso vs whip vs generic from log content. See `/flume` skill for details.

### Memory Leak Diagnosis (memleak)

**Trigger `/memleak`** when investigating memory growth, RSS increase, GC stalls, or event loop pauses on a running Python process. Also trigger when the user has `.pkl` tracemalloc snapshot files to analyze.

**Workflow:**
1. Confirm leak via `/proc/PID/status` RSS polling
2. Generate and inject `gc.callbacks` + `tracemalloc` script via gdb
3. Collect snapshots, diff to find growing allocations
4. Trace full call stacks to pinpoint the leak source

## Rule Files

Always loaded:
- Command line conventions: @~/.claude/rules/command-line.md
- Python conventions: @~/.claude/rules/python.md
- Code quality workflow: @~/.claude/rules/code-quality.md
- Agent triggers: @~/.claude/rules/agent-triggers.md
- Claims vs Hypotheses: @~/.claude/rules/claims-vs-hypotheses.md

Loaded by skills/agents that need them (not every session):
- `rules/github-issues.md` — GitHub issue creation, labels, sub-issues (`@technical-doc-writer`, `/sub-issue`)
- `rules/agent-teams.md` — Team protocols, chaining, escalation paths (`/pr-pipeline`, `/tdd`, `/incident`)
- `rules/zensical.md` — Zensical config and conventions (`@technical-doc-writer`)
- `rules/session-wrapup.md` — Session review (`/lessons-learned`)
- `rules/execution-efficiency.md` — Verify before executing; agent vs direct
