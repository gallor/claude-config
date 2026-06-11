---
name: incident
description: Spawn an Incident Response agent team — directed investigation or competing hypotheses based on symptom clarity
user-invocable: true
argument-hint: <incident description and symptoms>
---

# Incident Response Team

Create an agent team to investigate an incident or complex bug.

**Falsification-first.** Each hypothesis is eliminated by the smallest piece of counter-evidence, not by exhaustive verification. In Mode B, investigators actively try to disprove *each other's* hypotheses — one counterexample eliminates a branch. See `rules/claims-vs-hypotheses.md` § Falsification First.

> **Lead**: The lead is the parent Claude session that invoked this skill. It orchestrates the team, collects results, and makes decisions.

**Incident**: $ARGUMENTS

## Mode Selection

Analyze the symptoms and select the investigation mode:

- **Mode A (Directed)**: Use when there's a clear starting point — a stack trace, specific error log, known failing component, or single obvious hypothesis.
- **Mode B (Competing Hypotheses)**: Use when symptoms are ambiguous, multiple components could be at fault, or the cause isn't obvious from the symptoms alone.

If unsure, start with Mode A. Escalate to Mode B if directed investigation doesn't converge.

---

## Mode A: Directed Investigation

1. **Create team**: `TeamCreate` with name `incident-response`

2. **Create tasks**:
   - Task 1: "Investigate root cause: $ARGUMENTS" (assign to `debugger`)
   - Task 2: "Post-mortem documentation" (blocked by task 1)
   - Task 3: "Recommend detection improvements" (blocked by task 2)

3. **Spawn teammate**:
   - `debugger` — `@ultrathink-debugger` with prompt: "Investigate this incident: $ARGUMENTS. Use the Claims vs Hypotheses framework. If you need telemetry data, message the lead to spawn @observability-sentinel. Report your root cause findings to the lead."

4. **Expand as needed**:
   - If debugger needs telemetry → spawn `telemetry` as `@observability-sentinel`

5. **Shutdown incident team** once root cause is identified

6. **Fix** (if needed) — invoke `/tdd` with root cause as requirements. This runs as a separate team.

7. **Post-mortem** — spawn `analyst` as `@incident-analyst` (runs after fix is applied)

8. **Detection** — spawn `strategist` as `@observability-strategist` to recommend what telemetry would have caught this faster

### Escalate to Mode B when:
- 3+ hypotheses falsified without convergence (aligned with `/kpop` stuck detection)
- Debugger reports multiple plausible causes with no clear winner
- The fix for the suspected cause doesn't resolve the issue
- Symptoms suggest multiple interacting failures

---

## Mode B: Competing Hypotheses

1. **Create team**: `TeamCreate` with name `incident-response`

2. **Generate hypotheses**: Analyze the symptoms and form 3-5 distinct, falsifiable theories. Each hypothesis must be specific enough to be disproven (e.g., "connection pool exhaustion under >100 concurrent requests" — not "something with connections").

3. **Create tasks**:
   - One task per hypothesis: "Investigate hypothesis: [specific theory]" (assign to each investigator)
   - Task: "Gather telemetry evidence across all hypotheses" (assign to `telemetry`)
   - Task: "Post-mortem documentation including all hypotheses tested" (blocked by all investigation tasks)

4. **Spawn investigators** — one `@ultrathink-debugger` per hypothesis, named by theory:
   - `investigator-<shortname>` — prompt includes: "Investigate this hypothesis: [theory]. Your goal is twofold: (1) find evidence that supports OR refutes your hypothesis, and (2) actively try to disprove the other hypotheses. Message other investigators directly with counter-evidence. If you find definitive evidence for or against any hypothesis, broadcast it. The other hypotheses being investigated are: [list all hypotheses]."
   - `telemetry` — `@observability-sentinel` with prompt: "Gather telemetry data relevant to this incident: $ARGUMENTS. The team is investigating these hypotheses: [list]. Share relevant telemetry findings with all investigators. You are a shared resource — respond to data requests from any investigator."

5. **Lead monitors for convergence**:
   - Watch for investigators eliminating hypotheses
   - **Shut down investigators eagerly** as their hypothesis is eliminated — don't keep them running. If an eliminated hypothesis needs re-examination (e.g., new evidence surfaces), respawn.
   - Shut down `telemetry` once all remaining investigators have the data they need
   - When all but one hypothesis is eliminated, or investigators reach consensus, declare root cause
   - If two hypotheses survive and can't be distinguished, consider that multiple interacting failures may be the cause

6. **Post-mortem** — spawn `analyst` as `@incident-analyst` with prompt: "Write a post-mortem for this incident. Include ALL hypotheses that were investigated, the evidence for/against each, why each was eliminated or confirmed, and what the root cause turned out to be. This is critical for institutional knowledge."

7. **Detection** — spawn `strategist` as `@observability-strategist` with prompt: "Given this incident and the competing hypotheses that were tested, recommend telemetry improvements. Focus on: what data would have disambiguated the hypotheses faster? What alerts would have caught this before users reported it?"

8. **Shutdown incident team** once root cause is confirmed

9. **Fix** — invoke `/tdd` with confirmed root cause as requirements. This runs as a separate team.

## References

- `rules/agent-teams.md` — team protocols, escalation paths
- `rules/agent-triggers.md` — trigger conditions, dynamic escalation signals
