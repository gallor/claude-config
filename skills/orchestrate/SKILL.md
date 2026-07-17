---
name: orchestrate
description: Explicitly run the orchestrator workflow — triage a task, then either handle it with one cheap agent or fan out to deep-reasoner + fast-worker with Codex as a parallel peer reasoner
user-invocable: true
argument-hint: <task or problem to orchestrate>
---

# Orchestrate

Run the orchestrator workflow **on demand**. This does not fire from context — it
runs only when you invoke `/orchestrate`. The first thing it does is **triage**:
most tasks do not warrant deep analysis or a full fan-out, and paying for Opus +
Codex on a task a single cheap agent can finish is waste. Triage picks the
cheapest lane that fits, and only escalates to full parallel synthesis when the
task genuinely earns it.

**Task**: $ARGUMENTS

## Step 1 — Triage (always first)

Classify the task in `$ARGUMENTS` into exactly one lane. **Announce the chosen
lane and a one-line reason** before acting, so the triage decision is visible.

| Lane | The task is… | Route to | Fan out? |
|------|--------------|----------|----------|
| **A — Cheap/mechanical** | Decided work; the "what" is settled and only execution remains (boilerplate, formatting, rote edits, obvious tests, mechanical refactor) | One `@fast-worker` — or do it inline if it's a one- or two-line change | No |
| **B — Single specialist** | Squarely one documented specialty | That one specialist (see Precedence below) | No |
| **C — Reasoning-heavy, not high-stakes** | Needs real thinking, but a wrong answer is cheap to correct and not many things depend on it | One `@deep-reasoner`; act on its conclusion | No — **no Codex** |
| **D — High-stakes** | Expensive to get wrong: hard-to-reverse architecture, a subtle correctness call, or a design many things depend on; or cross-cutting with no single specialist fit | Full parallel synthesis (Step 2) | Yes |

**Precedence (lanes B/C):** a specific specialist beats the generic reasoner. If
the task is squarely a documented specialty — architecture design →
`@solution-architect`; reproduce-and-fix debugging → `@ultrathink-debugger`;
performance → `@performance-*`; migration → `@migration-specialist`; security →
`@security-sentinel`; etc. — route there (lane B). Use `@deep-reasoner` (lane C)
only when the reasoning is cross-cutting, spans systems, or no single specialist
fits (e.g. algorithm design).

**Bias toward the cheapest lane that fits.** When unsure between two adjacent
lanes, pick the cheaper one — you can always escalate after seeing its output.
Escalating late is cheap; a needless Opus + Codex fan-out is not.

For lanes A, B, and C: route, act on the result, report, and **stop**. Do not
continue into Step 2.

## Step 2 — Full orchestration (lane D only)

You (the main session) are the **orchestrator**: plan, decompose, delegate, and
synthesize. Keep your own context lean — hold the plan and the conclusions, not
the full working of any subagent.

1. **Spawn two independent reasoners in one turn**, both `run_in_background: true`:
   - `@deep-reasoner` (Opus) on the problem.
   - `codex:codex-rescue` via the Agent tool (`subagent_type: "codex:codex-rescue"`)
     on the *same* problem.
2. **Keep them blind to each other.** Neither sees the other's answer. Independent
   reasoning beats one answer plus a critique — it avoids anchoring and groupthink.
   Two genuinely independent solutions are worth more than one plus a review.
3. **Synthesize yourself.** Take the strongest reasoning from each, reconcile where
   they disagree, and commit to the final decision. Codex is a **peer, not a
   reviewer** — it produces its own solution; it does not rubber-stamp Opus.
4. **Decompose and delegate execution.** Break the resulting plan into units. Send
   decided, mechanical work to `@fast-worker`; keep judgment work with the
   appropriate specialist. Delegate the *doing*; hold the plan.
5. **Report** the synthesized decision and what was delegated.

### Codex guardrails

- Codex requires `/codex:setup` to be ready (verify if unsure).
- `codex:codex-rescue` is a **subagent, not a skill** — invoke it via the Agent
  tool with `subagent_type: "codex:codex-rescue"`. **Never** `Skill(codex:rescue)`
  — that re-enters the command and hangs the session.
- It is a thin forwarder that returns its output verbatim.

## Notes

- Invoking `/orchestrate` on a trivial task is harmless — triage routes it to lane
  A and it costs one cheap agent, not a fan-out. The gate exists precisely so that
  explicit invocation never forces the expensive path.
- The agents used here (`@deep-reasoner`, `@fast-worker`, `codex:codex-rescue`, and
  the specialists) remain directly `@`-callable outside this skill; `/orchestrate`
  is just the triage-and-fan-out entry point.
