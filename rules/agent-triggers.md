# Agent Trigger Definitions

This file defines when subagents should be automatically invoked.

## Automatic Triggers

### Pre-Action Triggers

| Before This Action | Invoke | Purpose |
|--------------------|--------|---------|
| Create a PR (`gh pr create`) | `/pr-pipeline` (team) or `@code-reviewer` (solo) | Review + docs in parallel |

### Post-Action Triggers

| After This Action | Invoke | Purpose |
|-------------------|--------|---------|
| Complete a feature implementation | `@code-quality-pragmatist` | Review for over-engineering |
| Claim task completion | `@karen` | Verify actual completion |
| Resolve a production incident | `@incident-analyst` | Post-mortem documentation |

### Context Triggers

| When This Context Is Detected | Invoke | Purpose |
|-------------------------------|--------|---------|
| Reasoning-heavy phase (architecture, complex debugging, algorithm design, hard trade-offs) with no single specialist fit | `@deep-reasoner` | Opus reasoning, advisory-only; returns a concise actionable conclusion. See [Orchestration Routing](#orchestration-routing) |
| Mechanical, decided work (boilerplate, formatting, simple edits, obvious tests, rote refactors) | `@fast-worker` | Haiku execution — fast and cheap. See [Orchestration Routing](#orchestration-routing) |
| High-stakes, hard-to-reverse decision | `@deep-reasoner` + `codex:codex-rescue` in parallel | Independent dual-reasoner synthesis. See [Orchestration Routing](#orchestration-routing) |
| Production incident or complex bug | `/incident` (team) or `@ultrathink-debugger` (solo) | Investigation with optional competing hypotheses |
| New feature or bug fix (test-first) | `/tdd` (team) or `@qa-sentinel` → `@code-craftsman` (solo) | TDD workflow |
| Bug requires deep debugging | `@ultrathink-debugger` | See [Debugger Invocation Criteria](#debugger-invocation-criteria) — present hypothesis to user before invoking |
| Architecture decision needed | `@solution-architect` | Design evaluation |
| Requirements are ambiguous | `@requirements-architect` | Clarify requirements |
| Writing documentation | `@technical-doc-writer` | Ensure quality docs |
| Implementing from design | `@code-craftsman` | Clean implementation |
| Running/writing tests | `@qa-sentinel` | Test strategy |
| Adding/modifying telemetry | `@observability-sentinel` | Instrumentation guidance |
| Designing what to measure | `@observability-strategist` | Metrics strategy |
| Reviewing own code before push | `/review` or `@code-reviewer` | Pre-push review with optional aspect filtering |
| Reviewing someone else's PR | `@code-reviewer` + `@technical-doc-writer` (parallel) | Review quality + verify newsfragments |
| Bug or investigation where cause isn't immediately obvious | `/kpop` | Default investigation protocol — use first, not after you're stuck |
| 3+ hypotheses falsified or cycling on similar approaches | `/creativity` | Boundary exploration to escape local optima (escalation within `/kpop`) |
| Root cause identified, user opts to fix (not file an issue) | `/tdd` | **Mandatory** — failing regression test before the patch. See `rules/claims-vs-hypotheses.md` § Falsification First "Post-diagnosis rule". Never fix-then-test. |

## Orchestration Routing

The main session is the **orchestrator**: plan, decompose, delegate, synthesize — keep your own context lean by handing the *doing* to subagents. These three triggers implement the tier routing (full rationale in `CLAUDE.md` § Orchestration Workflow).

**Precedence:** a specific specialist beats the generic reasoner. If the task is squarely a documented specialty — architecture design → `@solution-architect`, reproduce-and-fix debugging → `@ultrathink-debugger`, perf → `@performance-*`, etc. — route there. Use `@deep-reasoner` only when the reasoning is cross-cutting, spans systems, or no single specialist fits (e.g. algorithm design). This keeps the existing Context Triggers authoritative and `@deep-reasoner` as the catch-all for hard thinking.

**`@fast-worker` (Haiku, mechanical):** route decided, low-judgment work here — the "what" is already settled and only execution remains. The moment judgment is required (design, test strategy, unclear approach), `@fast-worker` escalates back rather than guessing. Do not send it work that hasn't been scoped.

**High-stakes parallel synthesis** (`@deep-reasoner` + `codex:codex-rescue`): for a decision that is expensive to get wrong (hard-to-reverse architecture, subtle correctness call, a design many things depend on):

1. Spawn **`@deep-reasoner`** (Opus) and **`codex:codex-rescue`** (via the Agent tool, `subagent_type: "codex:codex-rescue"`) on the *same* problem, both with `run_in_background: true`, in a single turn so they run concurrently.
2. **Keep them blind to each other** — neither sees the other's answer. Independent reasoning beats one answer plus a critique; it avoids anchoring and groupthink.
3. **Synthesize** the strongest reasoning from each yourself; reconcile disagreements and commit to the final decision.
4. Codex is a **peer, not a reviewer** — it produces its own solution, it does not rubber-stamp Opus. It requires `/codex:setup` to be ready. `codex:codex-rescue` is a **subagent, not a skill** — never `Skill(codex:rescue)` (it re-enters the command and hangs the session).

## Trigger Protocol

When a trigger condition is met:

1. **Check**: Is an agent team already active? If yes, spawn as teammate (see `rules/agent-teams.md`)
2. **Prefer skills**: If a skill exists for the workflow (`/pr-pipeline`, `/tdd`, `/incident`), use it — skills encode the full team orchestration
3. **Announce**: "Based on [trigger condition], invoking /skill-name" (or "@agent-name" for solo invocations)
4. **Invoke**: Use `Skill` tool (team skill) or `Task` tool (solo subagent)
5. **Report**: Summarize agent findings to user
6. **Act**: Implement agent recommendations (with user approval if significant)

## Debugger Invocation Criteria

Before invoking `@ultrathink-debugger`, **present a hypothesis to the user** explaining why the debugger is needed. The user decides whether to proceed.

**Format**: "I think this warrants `@ultrathink-debugger` because [hypothesis]. Should I invoke it?"

**Starting criteria** (invoke when the bug involves):
- Log file analysis and cross-referencing with source code
- Tracing execution across multiple modules or services
- Reproducing timing-dependent or intermittent failures
- Root cause is not evident from the stack trace alone

**Not needed for** (handle directly):
- Single-file bugs with obvious fixes
- Errors with clear stack traces pointing to the problem
- Configuration or typo issues

**Evolving this list**: When you present a hypothesis and the user approves, add the new criterion to the appropriate list above if it isn't already covered. This keeps the criteria grounded in real decisions.

## Dynamic Escalation

When a team or solo workflow is active, these signals trigger specialist escalation:

| Signal Detected By | Condition | Spawn |
|--------------------|-----------|-------|
| `@qa-sentinel` | Test suite wall-clock time increases >10% vs base branch, or a single test's duration increases >2x | `@performance-college-sprinter` |
| `@performance-college-sprinter` | Needs deep analysis or optimization | `@performance-usain-bolt` |
| `@performance-college-sprinter` | Needs rigorous benchmarks to quantify | `@performance-benchmark-monkey` |
| `@performance-usain-bolt` | Needs controlled comparative benchmarks or regression measurement | `@performance-benchmark-monkey` |
| `@performance-college-sprinter` or any teammate | Code review identifies memory-suspect patterns (object creation in tight loops, unbounded caches, materializing large iterators, buffer copies) that warrant profiling | `@performance-usain-bolt` (who then runs profiling tools) |
| `@code-craftsman` | Auth/DB/upload code touched, or `.rs` files with `unsafe` blocks | `@security-sentinel` |
| `@code-craftsman` | Needs instrumentation | `@observability-sentinel` |
| `@observability-sentinel` | "What should we measure?" | `@observability-strategist` |
| `@code-reviewer` | Over-engineering signals | `@code-quality-pragmatist` |
| `@code-reviewer` | Diff is C++-heavy (touches headers, wire formats, virtual interfaces, hot loops) | `@cpp-joe` |
| Any agent | Root cause unclear | `@ultrathink-debugger` |
| Any agent | Architectural concern | `@solution-architect` |

## Manual Invocation

Users can always explicitly request an agent:
- "Use @ultrathink-debugger to investigate this"
- "Have @solution-architect review this design"
- "Run @karen to check if this is actually done"
- "Ask @observability-strategist what metrics I should track"

## File Access Boundaries

**Agents should ONLY modify project files relevant to their task:**

| Agent | May Modify |
|-------|------------|
| `@technical-doc-writer` | `docs/`, `newsfragments/`, `*.md` in project |
| `@code-craftsman` | `src/`, source code files |
| `@qa-sentinel` | `tests/`, test files |
| `@ultrathink-debugger` | Source/test files (for fixes), logging only |
| `@performance-benchmark-monkey` | `benchmarks/`, `bench_*.py`, `*_benchmark.py`, benchmark config/results |

**Advisory-only agents (no file modifications):**
- `@observability-strategist`, `@observability-sentinel`
- `@incident-analyst`, `@tech-debt-tracker`
- `@solution-architect`, `@requirements-architect`
- `@karen`, `@code-quality-pragmatist`, `@code-reviewer`

**Agents must NEVER modify:**
- `~/.claude/` (agents, rules, settings, CLAUDE.md)
- Other agents' target files without explicit request

## Model Selection

| Model | Agents | Use When |
|-------|--------|----------|
| **opus** | `@ultrathink-debugger`, `@solution-architect`, `@performance-usain-bolt`, `@migration-specialist`, `@observability-strategist`, `@incident-analyst`, `@karen`, `@code-quality-pragmatist` | Deep reasoning, complex analysis, architectural decisions. Always uses Opus regardless of parent session model. |
| **sonnet** | All others | Standard tasks, structured work, systematic operations |
