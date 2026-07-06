---
name: kpop
description: Default investigation protocol — structured hypothesis testing with logging and stuck detection. Use first for any non-trivial bug, investigation, or implementation task.
user-invocable: true
argument-hint: <problem description>
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Edit", "Write", "Skill"]
---

# KPOP: Popper-style Scientific Problem-Solving

The default protocol for any non-trivial investigation. Use this **first** — not after you're already stuck. If the problem isn't immediately obvious from a stack trace or single-file read, start here.

This is for **doing** — debugging, implementing, investigating.

**Problem:** $ARGUMENTS

## Context Check

Check for relevant context in the project's `CLAUDE.md` or any `brain-*.md` files in the project root. If found, understand the larger goal. Your work should advance that goal.

## The Loop

**Restate the problem clearly** before starting.

All hypotheses and claims must follow `rules/claims-vs-hypotheses.md` — label uncertain reasoning as Hypothesis, only upgrade to Claim with evidence.

**Falsification-first.** Each hypothesis's Falsification step is the *smallest* test that could disprove it — not a broad verification. One failing case is enough to reject; one survival attempt is not enough to confirm. See `rules/claims-vs-hypotheses.md` § Falsification First.

```
while budget not exhausted:
  Hypothesis: State a specific causal explanation for the observed problem
  Prediction: What you expect to observe if true (and what would falsify it)
  Falsification: Run the simplest test that could disprove the hypothesis
  Result: Did the prediction hold? If falsified, reject and form new hypothesis
```

## Logging

Log each hypothesis and result **immediately as it happens** (don't batch).

- Log file: `_kpop/exp_log_{meaningful_name}.md`
- Create `_kpop/` if it doesn't exist
- Use a descriptive name based on the problem being solved

## Log Format

```markdown
# Experiment Log: <Problem Name>

**Started**: YYYY-MM-DD HH:MM
**Problem**: <Clear statement>

## Hypothesis 1
**H**: <hypothesis>
**P**: <prediction / falsification criteria>
**Test**: <what you did>
**Result**: Confirmed / Falsified / Inconclusive
**Next**: <what this tells us>

## Hypothesis 2
...

## Resolution
**Outcome**: <what solved it or what we learned>
**Time spent**: <duration>
```

## Stuck Detection

If any of these are true, **stop and invoke `/creativity`**:

- 3+ hypotheses falsified without meaningful progress
- You're proposing minor variations of the same approach
- Each new hypothesis feels like a small parameter tweak
- You've been circling the same failure mode

After `/creativity` generates structurally distant alternatives, return to KPOP with a fresh hypothesis from that output.

Log the creativity pivot in your experiment log:
```markdown
## Creativity Pivot
**Trigger**: <why you invoked creativity>
**Alternatives generated**: <brief list>
**Selected**: <which one you're pursuing and why>
```

## Resolution

When a root cause is identified, ask: **fix or file an issue?**

- **File issue** → create GH issue with the repro and diagnosis. Done.
- **Fix** → invoke `/tdd` with the root cause as requirements. **Do not patch first.** The failing regression test must come before the fix — it is the falsifying evidence for the diagnosis and the verification for the fix. See `rules/claims-vs-hypotheses.md` § Falsification First.

When the problem is resolved:
1. Write the Resolution section in the log
2. If applicable, update the relevant `CLAUDE.md` or `brain-*.md` task checkboxes
3. Add significant findings (design invariants, non-obvious behaviors) as candidates for `/lessons-learned`
