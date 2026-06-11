---
name: creativity
description: Boundary exploration for when you're stuck producing small variations of the same idea. Generates structurally distant alternatives within the same formal system.
user-invocable: true
argument-hint: <description of current state and what's been tried>
allowed-tools: []
---

# Boundary Exploration Mode

You are stuck producing small local variations of the same idea.

**Do NOT** introduce new frameworks, objectives, or representations.

Stay within the same formal system, but explore its boundaries.

**Current state:** $ARGUMENTS

## Process

Identify the core assumptions of the current idea. For each one:

1. **Push it to an extreme limit** — what happens at 10x, 100x, infinity?
2. **Consider its negation** — what if the opposite were true?
3. **Consider asymptotic scaling or pathological edge cases** — where does it break?

Generate an idea that is **structurally distant** from the original but obeys the same rules.

## Quality Check

If an idea could be reached by a small parameter tweak, **discard it and go further**.

Do not evaluate or prune yet. Your goal is boundary exploration, not refinement.

## Output

Present 3-5 structurally distinct variations, each with:
- Which assumption was challenged
- How it was transformed
- The resulting idea (brief description)
