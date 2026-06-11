# Agent Teams Reference

Loaded by team skills (`/pr-pipeline`, `/tdd`, `/incident`). Not loaded into every session.

## When to Use Teams vs Subagents

| Use **Subagents** When | Use **Agent Teams** When |
|------------------------|--------------------------|
| Task is focused, result-only | Multiple agents need to coordinate with each other |
| Steps are strictly sequential | Work can be parallelized across agents |
| Only one agent needed | 2+ agents working concurrently |
| Low token budget | Coordination value justifies higher token cost |

> **Prerequisite**: Agent teams require `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` enabled in `settings.json` or environment.

## Team Workflows

Team workflows are implemented as skills. Invoke the skill for full orchestration.

| Workflow | Skill | Trigger | Core Roster | Solo Fallback |
|----------|-------|---------|-------------|---------------|
| PR Pipeline | `/pr-pipeline` | PR creation | `@code-reviewer`, `@technical-doc-writer` | `@code-reviewer` → `@technical-doc-writer` sequentially |
| TDD Feature Dev | `/tdd` | Feature or bug fix (test-first) | `@qa-sentinel`, `@code-craftsman` | `@qa-sentinel` → `@code-craftsman` sequentially |
| Incident Response | `/incident` | Production incident | `@ultrathink-debugger` (×N), `@observability-sentinel` | `@ultrathink-debugger` solo |

## Team Protocol

When a team workflow is triggered:

1. **Announce**: "Creating [team-name] team for [purpose]"
2. **Create team**: `TeamCreate` with descriptive name
3. **Create tasks**: `TaskCreate` to break work into assignable units
4. **Spawn core roster**: Spawn teammates with `team_name` parameter
5. **Monitor**: Watch for escalation signals in teammate messages
6. **Escalate**: Spawn specialist teammates when triggers are detected (see `rules/agent-triggers.md` § Dynamic Escalation)
7. **Eager shutdown**: When a teammate finishes its task and has no pending work, shut it down immediately. Don't let idle agents burn context. If the teammate is needed again later (e.g., escalation reveals new work), respawn it.
8. **Synthesize**: Collect results when tasks complete
9. **Shutdown**: Shut down any remaining teammates, then `TeamDelete`

## Team-to-Team Handoff

Teams can chain into other teams. When a TDD Feature Dev Team completes implementation, the lead shuts down that team and creates a PR Pipeline Team for submission. Context is passed via the task descriptions and PR diff, not shared memory.

## Agent Chaining (Solo Session)

Sequential subagent invocations for when teams aren't needed.

### Feature Development Chain
```
Feature Request
    │
    ▼
@requirements-architect  ──▶  Clarify requirements
    │
    ▼
@solution-architect      ──▶  Design approach
    │
    ▼
@observability-strategist ──▶  What metrics matter?
    │
    ▼
@code-craftsman          ──▶  Implement
    │
    ▼
@observability-sentinel  ──▶  Telemetry implementation
    │
    ▼
@qa-sentinel             ──▶  Test
    │
    ▼
@code-quality-pragmatist ──▶  Review complexity
    │
    ▼
@code-reviewer           ──▶  Local review before PR
    │
    ▼
PR Created
    │
    ▼
@technical-doc-writer    ──▶  Documentation
```

### Incident Response Chain
```
Incident Detected
    │
    ▼
@ultrathink-debugger     ──▶  Root cause analysis
    │
    ▼
@observability-sentinel  ──▶  Query telemetry data
    │
    ▼
(Fix applied)
    │
    ▼
@incident-analyst        ──▶  Post-mortem
    │
    ▼
@observability-strategist ──▶  Improve detection
```

## Specialist Escalation Paths

### Performance
1. `@performance-college-sprinter` catches obvious issues during review
2. If deeper analysis/optimization needed → `@performance-usain-bolt`
3. If rigorous benchmarks needed → `@performance-benchmark-monkey`
4. If architectural changes needed → `@solution-architect`

**Pre-assessment requirement:** Before reporting findings, cross-reference open PRs (`gh pr list`) to filter out issues already addressed by in-flight work. The deliverable is "what's left after open PRs land?" not a raw list of findings.

### Observability
1. `@observability-sentinel` handles implementation questions
2. If "what should we measure?" → `@observability-strategist`
3. If architectural implications → `@solution-architect`

### Code Review
1. `@code-reviewer` performs standard review (quality, correctness, style, comments)
2. If over-engineering signals detected → `@code-quality-pragmatist`
3. If architectural concerns → `@solution-architect`

**Over-engineering signals** (trigger escalation): see `rules/code-quality.md` §@code-reviewer

### Security

| When | Invoke |
|------|--------|
| Auth/login code changes | `@security-sentinel` |
| Database query changes | `@security-sentinel` |
| File upload handling | `@security-sentinel` |
| New API endpoints | `@security-sentinel` |
| Dependency updates | `@security-sentinel` (for CVE check) |

### Migrations

| When | Invoke |
|------|--------|
| Replacing a library | `@migration-specialist` |
| Python version upgrade | `@migration-specialist` |
| Handling deprecation warnings | `@migration-specialist` |
| Breaking API changes | `@migration-specialist` |

### Lead Tasks

| When | Invoke |
|------|--------|
| Post-incident analysis | `@incident-analyst` |
| Tech debt prioritization | `@tech-debt-tracker` |
