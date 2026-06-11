# Code Quality

**Related agents**:
- `@code-craftsman` - Efficient implementation following best practices
- `@code-quality-pragmatist` - Review for over-engineering and unnecessary complexity
- `@code-reviewer` - PR review, including inline comment assessment
- `@solution-architect` - System design and architectural decisions

## Implementation Workflow

1. `@requirements-architect` or `@solution-architect` provides design
2. `@code-craftsman` implements the solution
3. `@qa-sentinel` validates through testing
4. `@code-quality-pragmatist` reviews for unnecessary complexity

## When to Use Each Agent

### @code-craftsman
- Implementing features from a design
- Refactoring existing code
- Performance optimization
- Following codebase conventions

### @code-quality-pragmatist
- After implementing features - review for over-engineering
- When code feels unnecessarily complex
- Checking for premature abstractions

### @code-reviewer
- PR reviews (own code or others')
- Code quality, correctness, style
- Inline comment assessment (see below)
- **Escalate to `@code-quality-pragmatist`** when detecting:
  - Excessive abstraction layers for the task at hand
  - New interfaces/classes that seem unnecessary
  - Over-use of design patterns
  - Configuration/options beyond current requirements
  - "Future-proofing" that adds complexity now

### @solution-architect
- Designing new services or major features
- Technology selection decisions
- API design
- Evaluating architectural trade-offs

## Agent Collaboration

### @code-reviewer → @code-quality-pragmatist

During review, `@code-reviewer` should invoke `@code-quality-pragmatist` when it detects **smell signals**:

| Signal | Example |
|--------|---------|
| Abstraction for one use | Factory that creates one type |
| Premature generalization | Config options no one uses yet |
| Interface with single impl | `IFooService` + `FooService` |
| Excessive indirection | 3+ layers to do simple operation |
| "Just in case" code | Error handling for impossible states |

When escalating, `@code-reviewer` should pass:
1. The specific files/lines of concern
2. The suspected over-engineering pattern
3. Context on what the PR is trying to accomplish

## Backwards Compatibility (Libraries)

When the project's `CLAUDE.md` identifies it as a library, backwards compatibility is critical. All agents (`@code-craftsman`, `@code-reviewer`, `@code-quality-pragmatist`, `@qa-sentinel`) must enforce:

- **Never remove or rename public attributes, parameters, or methods** without a deprecation shim. Use the project's `@deprecated` decorator (e.g., `Core.utility.functions.deprecated`) if available; otherwise use `warnings.warn(DeprecationWarning)`.
- **Never change function signatures** in ways that break existing callers (positional arg reorder, required param rename).
- When replacing a field, keep the old name accessible via a `@property` + `@deprecated(details="use new_name")` that delegates to the new one.
- `@qa-sentinel` must include tests verifying deprecated accessors still work and emit the expected warning (`FutureWarning` for `@deprecated`, `DeprecationWarning` for raw `warnings.warn`).
- `@code-reviewer` should flag any public API removal or rename that lacks a deprecation path.
- **Assume backwards compatibility unless the user explicitly says a breaking change is acceptable.** Do not ask; default to preserving the existing API.

## Evidence Requirements

All agents and the main session must follow `rules/claims-vs-hypotheses.md`. Key rules for implementation work:

- **Performance claims require evidence.** "X is faster" is a Hypothesis until backed by `scalene` profile or benchmark data. This applies to code you write, code you review, and suggestions you make.
- **Perf-motivated complexity requires justification.** If code is more complex "for performance", the profile/benchmark that motivated it must exist. Without evidence, prefer the simpler approach.
- **Don't accept unverified claims from other agents.** If an agent says "this optimization improves throughput by 30%", ask for the data.

## Performance Claims

- **Verify micro-optimization suggestions against surrounding work.** Don't propose changes like "pre-allocate `[None] * N` to avoid list reallocations" without measuring. When each loop iteration does heavy work (object construction, buffer operations, I/O), `list.append` overhead is in the noise. CPython's over-allocation strategy (12.5% growth) makes realloc cheap for pointer arrays.

## Before Filing Tech-Debt Issues

Code that has been stable for years is usually stable *because* nobody needs to touch it. Refactoring it is churn: reviewers context-load on unfamiliar code, risk is non-zero, and the payoff (future maintainability) never gets collected because no future maintenance was coming. Before filing a tech-debt refactor issue, check the file's git history:

```bash
git log --follow --format="%ai %h %s" <file> | head -5
```

**Staleness filter** — skip filing if either holds:
- **≤ 3 total commits** on the file (typically just initial import plus trivial touches), OR
- **≥ 2 years** since the last commit

**Correctness bugs are exempt** — a confirmed bug (wrong behavior, not just complexity) in stale code is still worth fixing, but as a *surgical one-line PR*, never bundled with a refactor.

**Mechanical fixes are exempt** — `ruff --fix` style sweeps are low-risk even on stale files; the staleness filter applies to complexity refactors and redesigns, not auto-fix cleanups.

Applies to `@tech-debt-tracker` and to ad-hoc filing from the main session. When running tools like `ruff-plr` across a repo, use this filter to triage findings before turning them into issues.

## Refactoring

- When moving or consolidating files (e.g., tests to benchmarks), check for pre-existing bugs in the moved code

## PR Descriptions

- Describe what the code does relative to the base branch, not how it evolved during development
- Incremental changes made during a session (e.g., "changed X to Y", "removed redundant copy") should not appear as separate bullets — they're implementation details, not features
- Benchmark numbers need multiple runs; single-run speedups vary ±5%. Round to one decimal.

## Newsfragments (Towncrier)

- **Use markdown formatting, not reStructuredText (RST).** Fragment content should be plain text or markdown.
- **Multiple fragments per issue:** call `towncrier create {number}.{type}.md --content "..."` repeatedly. Towncrier auto-suffixes duplicates (`.1`, `.2`, etc.). Do not manually add suffixes to the filename.
- **One sentence per fragment.** Each fragment should be a single sentence describing the change.

## Writing Style

- Never use em dashes. Use commas, semicolons, parentheses, or separate sentences instead.

## Inline Comments

Minimize inline comments. Code should be self-documenting through clear naming and structure.

**Comment when:**
- Explaining **why**, not what (non-obvious decisions)
- Documenting **workarounds** for bugs (with issue/ticket links)
- Clarifying **business logic** that isn't evident from code
- Explaining **regex or complex expressions**
- Justifying **performance trade-offs**
- Noting **security considerations**

**Do not comment:**
- What the code does (the code shows this)
- Restating function/variable names
- TODOs without tickets
- Commented-out code (delete it)
