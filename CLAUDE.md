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
| `@deep-reasoner` | opus | Reasoning-heavy phases, architecture, complex debugging, algorithm design — advisory-only, returns a concise actionable conclusion |
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
| **HAIKU (Mechanical Execution)** |
| `@fast-worker` | haiku | Boilerplate, formatting, simple edits, obvious tests, rote refactors — executes a decided spec efficiently, escalates on judgment |

## Orchestration Workflow

The orchestrator workflow is **explicit-only** — run it by invoking the **`/orchestrate`** skill. It does not fire from context. Its first step is always **triage**: most tasks do not warrant deep analysis or a full fan-out, so `/orchestrate` routes to the cheapest lane that fits and only escalates to parallel synthesis when a task genuinely earns it.

**Triage lanes (in `/orchestrate`):**

| Lane | The task is… | Route to |
|------|--------------|----------|
| Cheap/mechanical | Decided work, only execution remains | One `@fast-worker`, or inline for a one-liner |
| Single specialist | Squarely one documented specialty | That specialist (architecture → `@solution-architect`, debugging → `@ultrathink-debugger`, perf → `@performance-*`, …) |
| Reasoning-heavy, not high-stakes | Needs real thinking, cheap to correct if wrong | One `@deep-reasoner` (no Codex) |
| High-stakes | Expensive to get wrong, hard to reverse, or cross-cutting | Parallel synthesis (below) |

Only the high-stakes lane fans out. As orchestrator (the main session) your job there is to plan, decompose, and synthesize — not to burn your own context on work a subagent can do. Keep your context lean: delegate the doing, hold the plan.

**Codex as a peer reasoner.** Codex is a cracked engineer on par with `@deep-reasoner`, reasoning from a different perspective (different model, different training). Treat Codex as a **peer, not a reviewer** — it is not there to rubber-stamp Opus's answer; it is there to produce its own.

Invoke it as the **`codex:codex-rescue` subagent via the Agent tool** (`subagent_type: "codex:codex-rescue"`), or by typing the `/codex:rescue` command. It is a subagent, **not** a skill — never call `Skill(codex:rescue)` (it re-enters the command and hangs the session). For the parallel path below, spawn it with `run_in_background: true` so it runs concurrently with the Opus reasoner. Codex is a thin forwarder that returns its output verbatim; requires `/codex:setup` to be ready (already verified in this environment).

**High-stakes decisions — parallel synthesis.** For a decision where being wrong is expensive (architecture that's hard to reverse, a subtle correctness call, a design that many things depend on):

1. Task **`@deep-reasoner` (Opus)** and **Codex (`codex:codex-rescue`)** on the *same* problem, **in parallel** — spawn both as background agents in one turn.
2. **Do not show either one the other's answer** — independent reasoning avoids anchoring and groupthink; two genuinely independent solutions are worth more than one plus a critique.
3. **Synthesize the best of both** yourself. Take the strongest reasoning from each, reconcile where they disagree, and form the final decision.
4. Keep your own context lean throughout — hold the question and the two conclusions, not the full working of either.

`@deep-reasoner`, `@fast-worker`, and `codex:codex-rescue` remain directly `@`-callable at any time; `/orchestrate` is the triage-and-fan-out entry point, not a gate on the individual agents.

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
| `/orchestrate` | `/orchestrate <task>` | Triage, then one cheap agent or parallel `@deep-reasoner` + `codex:codex-rescue` synthesis (high-stakes only) |
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
