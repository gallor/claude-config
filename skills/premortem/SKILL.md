---
name: premortem
description: Predictive failure analysis — imagine the system has already failed and work backwards to find why. Use before shipping, merging, or deploying to surface non-obvious failure modes. Complements /kpop (diagnostic) and /review (correctness). Not for debugging existing failures — use /kpop for that.
user-invocable: true
argument-hint: <system, PR, design, or change to analyse>
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Skill"]
---

# Pre-mortem: Predictive Failure Analysis

Assume the system, change, or design described in `$ARGUMENTS` has already failed in production. Your job is to reconstruct *why* — then verify which failure modes are actually reachable given the current code.

**Relationship to /kpop:** kpop is diagnostic (something broke — find the cause). Pre-mortem is predictive (nothing broke yet — find what could). Both use Popperian falsification. Run pre-mortem *before* review or deployment; run kpop *after* a failure is observed.

**Problem:** $ARGUMENTS

## Phase 1: Read the System

Before generating failure modes, read the relevant code, diff, or design. Understand:
- What does this change/system actually do?
- What are its dependencies and failure boundaries?
- What invariants does it rely on?

Do not generate failure modes from imagination alone — ground them in the actual implementation.

## Phase 2: Generate Failure Scenarios

Imagine it is 3 months from now. The system has failed. Generate failure scenarios across these dimensions:

| Dimension | Questions to ask |
|-----------|-----------------|
| **Correctness** | Wrong output, silent data corruption, off-by-one, race condition |
| **Reliability** | Crashes under load, fails on edge input, cascades to dependents |
| **Performance** | Latency cliff, memory leak, O(n²) hiding in normal load |
| **Operational** | Cannot roll back, hard to debug when it fails, no signal before it breaks |
| **Integration** | Breaks callers not in this diff, protocol mismatch, version skew |
| **Security** | Privilege escalation, injection, credential exposure, auth bypass |

Generate 6–12 candidate scenarios. Be specific — "the retry loop doesn't bound" is better than "it could fail under load."

## Phase 3: Falsify Each Scenario

For each candidate, verify whether the code actually allows it. This is the falsification pass — most scenarios won't survive it.

```
Scenario: <description>
Reachable?: Read the relevant code path. Does it actually allow this failure?
Evidence: <file:line or reasoning>
Verdict: SURVIVES | FALSIFIED
```

A scenario is **falsified** if:
- The code explicitly guards against it
- The invariant it relies on is enforced elsewhere
- It requires a precondition that cannot be met

A scenario **survives** if:
- No guard exists
- The guard exists but has a gap (e.g. only checks the happy path)
- You cannot rule it out within 2–3 reads

**Budget:** spend at most 3 tool calls per scenario (one `Read` + one `rg` + one follow-up). If you can't falsify within that budget, the scenario survives — flag it as unverified.

## Phase 4: Triage Survivors

For each surviving scenario, assess:

| Attribute | Values |
|-----------|--------|
| **Likelihood** | Low / Medium / High |
| **Impact** | Nit / Degraded / Outage / Data loss |
| **Detectability** | Loud (immediate error) / Quiet (silent corruption) / Invisible (no signal) |
| **Mitigations** | Existing defences, monitoring, rollback options |

Sort by `Impact × (1 + Invisible)` — quiet failures rank above loud failures of equal impact.

## Phase 5: Output

Present surviving scenarios as a prioritised list:

```
## Pre-mortem: <subject>

### High Priority
🔴 **<scenario name>** — Impact: Outage | Likelihood: Medium | Detectability: Quiet
<one paragraph: what fails, how it manifests, why current code allows it>
Mitigation: <concrete suggestion>

### Medium Priority
🟠 ...

### Low Priority / Informational
🟡 ...

### Falsified (not a risk)
~~<scenario>~~ — <one line: what rules it out>
```

**Do not surface falsified scenarios as warnings** — a dismissed risk presented alongside real ones dilutes the signal. The falsified list is for audit purposes only.

## When to chain

- Surviving scenarios with `[critical]` impact → invoke `/kpop` to investigate further before shipping
- Surviving scenarios that are design-level → pass to `@solution-architect` or `/grill-me`
- After a real failure matches a pre-mortem scenario → run `/lessons-learned` to capture it
