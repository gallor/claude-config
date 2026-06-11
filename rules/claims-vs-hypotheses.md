# Claims vs Hypotheses

**Core Principle:** Label uncertain reasoning as **Hypothesis**; only promote to **Claim** with explicit evidence.

This applies to all agents and the main session. Performance assertions, root cause theories, optimization suggestions, and architectural trade-off arguments all require evidence before they are stated as fact.

## Language Guidelines

- **Hypothesis**: "suggests", "may", "likely", "indicates", "should be faster"
- **Claim** (with evidence): "shows", "demonstrates", "causes", "measured at", "profile confirms"

## Hypothesis Structure

For each Hypothesis, include:
- **Hypothesis**: concise, falsifiable statement
- **Predictions**: measurable outcomes if true
- **Test**: minimal experiment to validate (what to run, what to measure, pass/fail criteria)
- **Confounders**: likely alternatives and controls

## Test Before You Act

**Do not build on a hypothesis.** Run the minimal test first, then act on the result.

This is the most common failure mode: forming a plausible hypothesis and immediately investing effort (writing a large repro, building a fix, refactoring code) before validating it. The test defined in the Hypothesis Structure above is not documentation; it is the *next step*.

| Wrong | Right |
|-------|-------|
| "Hub is dropping messages" → build full service repro | "Hub is dropping messages" → 10-line script comparing sent vs received hashes |
| "This function is slow" → rewrite it | "This function is slow" → profile it |
| "The cache is stale" → add invalidation logic | "The cache is stale" → log cache hits/misses and check |

**Scale your investigation to the hypothesis, not the fix.** The smallest script, query, or log check that can falsify the hypothesis is always the right first move. If the hypothesis survives, *then* scale up.

**When the user redirects you, treat it as a falsification signal.** If the user says "are you sure?" or "try something simpler," your current hypothesis or approach has insufficient evidence. Step back, restate the hypothesis, and define a smaller test.

## Falsification First (Testing and Debugging)

**One counterexample beats broad verification.** Falsification is asymmetrically cheaper: proving code wrong needs one failing input; proving it right needs infinitely many.

- **First move:** "what is the smallest input that would falsify this?" Find it before building test suites, repros, or instrumentation.
- **Stop on first failure.** One counterexample is enough to fix. Don't keep scaffolding verification after you have it.
- **For confidence (not bugs), maximize variety.** Property-based tests, fuzzing, adversarial inputs — not deeper checks of the same scenarios.
- **Epistemic decoupling:** once the code survives enough varied attacks, it doesn't matter whether an LLM, a junior, or a senior wrote it. The loop determines quality, not the source.

| Wrong | Right |
|-------|-------|
| Add 30 unit tests to verify correctness | Write 1 property test; let Hypothesis find the counterexample |
| Build a full harness for a flaky bug | Find one input that reliably reproduces it, then fix |
| Verify the fix on the happy path | Attack it with edge cases; failing to break it is the evidence |

**Post-diagnosis rule: failing test before fix.** When debugging identifies a root cause and the user opts to fix (not file an issue), the next step is *always* a failing regression test — never the patch. The test is the falsifying evidence that proves the diagnosis and the verification that proves the fix. Invoke `/tdd`, or write the failing test manually first, then fix. "I'll add a test after" is the anti-pattern: without the failing-first step, you have no proof the test actually covers the bug.

## Upgrade Path: Hypothesis → Claim

A Hypothesis becomes a Claim when backed by evidence. The type of evidence depends on the domain:

| Domain | Required Evidence |
|--------|-------------------|
| **Performance** | `scalene` profile, benchmark data, or timing measurements with before/after comparison |
| **Debugging** | Failing test that reproduces the issue; test passes after the fix |
| **Correctness** | Code output, test results, or log evidence |
| **Architecture** | Concrete examples of the failure mode (not "might break someday") |

## Code Review

Review findings are hypotheses until verified against the actual code. A diff shows changes, not the full picture; surrounding context, call sites, and runtime behavior can all invalidate what looks obvious from the diff alone.

**Before reporting a finding, verify it:**
- "This is dead code" → grep for callers, including dynamic dispatch and string-based lookups
- "This variable is unused" → check if it's accessed via `getattr`, `__dict__`, or framework magic
- "This branch is unreachable" → trace the actual call sites, not just the local function
- "This is a bug" → construct (mentally or actually) the input that triggers it
- "This was removed" → confirm the `-` prefix in the diff; unchanged lines between hunks are still present

**Scale the verification to the claim's severity.** A nit about naming doesn't need a test. A claim that something is broken or a security issue does. If you'd flag it as `[critical]` or `[issue]`, you should have verified it first.

| Wrong | Right |
|-------|-------|
| "This catch block swallows errors" → flag it | Check what the callers expect; maybe swallowing is intentional |
| "This function has no callers" → suggest removal | `grep`/`rg` for all references including dynamic ones |
| "This duplicates X" → suggest consolidation | Read both implementations; they may differ in subtle ways |
| "Missing null check" → flag as critical | Trace whether null is actually possible at that call site |

**Do not report findings you haven't verified.** A wrong review comment wastes more time than a missing one; the author has to investigate, explain why it's not an issue, and the review thread grows. Five verified findings are worth more than fifteen guesses.

## Performance-Specific Rules

- **"X is faster than Y"** is always a Hypothesis until measured
- Use `scalene` as the default profiler (CPU + memory, low overhead, line-level granularity)
- Benchmark claims require multiple runs with statistical analysis (mean, stdev, CI)
- Micro-optimization claims must be measured against surrounding work; don't optimize noise
- When reviewing code that was written "for performance", require the profile/benchmark that motivated it

### Memory is a First-Class Dimension

Performance is not just CPU time. Every optimization, implementation decision, and benchmark must consider memory impact alongside speed:

- **Allocation rate matters as much as throughput.** High allocation churn causes GC pressure, which causes latency spikes and tail latency. An optimization that saves CPU but increases allocations can be a net regression.
- **Always report both CPU and memory.** `scalene` provides both in a single run. Never report only timing; always include allocation data.
- **Common memory-blind mistakes:**
  - Caching for speed without measuring the memory cost
  - Materializing iterators/generators into lists "for convenience"
  - Creating temporary objects in hot loops (dataclasses, dicts, tuples, formatted strings)
  - Buffer copies where views/memoryviews would work
  - Holding references that prevent GC (closures, default mutable args, module-level caches)
- **When proposing an optimization:** state the expected memory impact alongside the speed impact. "This should be 2x faster" is incomplete; "this should be 2x faster with similar allocation rate" or "this trades 20% more memory for 2x speed" is a proper Hypothesis.

This applies regardless of language. The patterns are universal; the tools differ.

## Anti-Patterns

- Stating "this is more efficient" without profiling → Hypothesis, not a Claim
- Rejecting a simpler approach "because it's slower" without measurement → requires evidence
- Proposing an optimization based on intuition → label as Hypothesis, then test
- Accepting a perf claim from another agent without data → flag it
- **Reporting only CPU impact** when the change affects allocation patterns → incomplete evidence
- **Building a large reproduction before a minimal one** → the 10-line script that falsifies the hypothesis is always step 1
- **Blaming an external system without verifying** → "the server is wrong" requires evidence just like "the code is wrong"
- **Scaling effort to the fix instead of the hypothesis** → if you haven't proven the root cause, don't build the solution
- **Flagging a review finding without reading surrounding code** → the diff is not the whole file; verify before reporting
- **Claiming code is dead/unused from the diff alone** → grep first; dynamic dispatch and framework magic hide callers
- **Reporting more unverified findings over fewer verified ones** → wrong findings waste the author's time
