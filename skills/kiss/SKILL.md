---
name: kiss
description: Keep It Simple, Stupid. Tier an abstraction (A/B/C) before building or refactoring. Applies an adversarial named-consumer test to typed fields — auto-fails "we might want," "for consistency," "future-proofing" justifications — and biases toward the minimum that solves the stated goal. Use when designing error types, config schemas, struct hierarchies, discriminated unions, or when something already shipped "feels heavy." Language-agnostic.
user-invocable: true
argument-hint: "<thing being designed or reviewed>"
allowed-tools: ["Read", "Bash", "Grep", "Glob"]
---

# KISS — Keep It Simple, Stupid

Three-tier decomposition (A/B/C) makes the cost and value of each design
step explicit. A single discipline test stops typed fields, variants,
layers, and abstractions from accumulating without a named consumer.

Language-agnostic. Applies to Rust enums, Python exception classes,
TypeScript discriminated unions, Go error types, GraphQL schemas,
config layouts, ORM models, REST resource shapes, internal APIs.

## When to invoke

- **Before** building a new error type, config schema, abstraction layer,
  or any structured representation
- **After** implementing something that "feels heavy" — review before it
  lands, while reduction is still cheap
- When `@code-quality-pragmatist` flags over-engineering signals
- When asked to refactor a typed surface that has accumulated fields
  without consumers
- When choosing between "fully structured" and "stringly-typed"

## The Three Tiers

**Tier A — Minimum viable.** The smallest implementation that solves the
*stated* goal. No typed fields beyond what's required to make the goal
work. Often a tuple, a formatted string, a flat map, a single function.
Default here unless evidence requires more.

**Tier B — Sweet spot.** Tier A + structure for fields with a *named
programmatic consumer*. A field is structured only when you can point
to the call site (in this codebase, a downstream consumer, or a public
API contract) that will pattern-match on it.

**Tier C — Full structure.** Tier B + typed fields for *anticipated*
future consumers, full discriminated-union variants, dedicated helper
types, parametric generics. Almost always overshoots until real usage
proves it necessary.

The cost curve is roughly linear in LoC; the value curve flattens
sharply between B and C. Most designs land at C and need walking back.

## The Discipline Test

### Prospective (designing new code)

> **Name a caller that will pattern-match on this field.**

If you can't, it's a `format!` argument (Rust), an f-string interpolation
(Python), a template string (TypeScript), a `fmt.Sprintf` (Go) — not a
typed field.

Applies recursively: if the caller you name only Display-formats the
field, that's still not a programmatic consumer. The bar is *behaviour
that branches on the field's value or type.*

Hypothetical future callers fail the test. So do "for consistency" and
"better DX" justifications. These are Hypotheses (per
`rules/claims-vs-hypotheses.md`); the test asks for the evidence that
promotes them to Claims.

### Retrospective (existing code)

> **Delete the field. Run tests + grep for the name. What surfaces?**

Real consumers show up as breakage; dead structure shows up as nothing.
The empirical dual to the prospective test — useful when the code has
already shipped and observable consumers (or their absence) beat
opinion. Pair it with `rules/claims-vs-hypotheses.md` § Falsification
First: one breakage is enough; you don't need to enumerate all callers.

### Sharper bar for shared / library / wire APIs

The default test is "name *one* programmatic consumer." For surfaces
that cross trust boundaries (published libraries, wire protocols,
multi-team APIs, persistence formats) raise the bar to:

> **Name two independent consumers, OR one consumer plus a documented
> evolution constraint.**

Single consumer at a public surface = inline at the call site or expose
a narrower API. Two independent consumers = the abstraction is paying
its rent. An evolution constraint (semver, wire compatibility,
forward-compat contract) substitutes for the second consumer because
the *future-you-can't-name* is contractually real, not hypothetical.

## Workflow

1. **State the goal** in one sentence. ("Make error logs correlatable
   to a connection." "Distinguish billing-eligible from internal users.")
2. **Decompose** the design into tiers A/B/C. Estimate LoC for each.
3. **Apply the discipline test** to every typed field at every tier.
4. **Recommend** a tier with rationale. Bias to A; B requires named
   consumers; C requires multiple named consumers and a stable surface.
5. **(If reviewing existing code)** Identify specific overshoots —
   fields, variants, or layers that fail the test — and propose the
   reduction.

## Common overshoots to watch for

| Pattern | Tell |
|---|---|
| Single-implementation interface | `IFooService` + `FooService` with one impl ever |
| Factory / builder for one type | `FooFactory.create()` returning the only `Foo` |
| Indirection layers | 3+ hops (wrapper → adapter → client) to reach the operation |
| Dependency injection for non-swappable deps | Constructor takes `Clock`, only `SystemClock` exists, never tested with another |
| Error handling for impossible states | `if x is None` after `x = make_x()` that can't return None |
| Discriminator enums for two cases | `enum Role { A, B }` when only `&'static str` is consumed |
| Input parameters carried in error variants | "What was the query?" — the caller already knows |
| Layered context structs | Display only reads 2 of N fields |
| Config options for a single internal call site | One caller, one value |
| Discriminated unions before the second variant exists | "Future-proofing" |
| Generic parameters before a second concrete type exists | Same |
| Ceremony to satisfy a lint you opted into | `Box<>` for `result_large_err`, `Arc<>` for non-shared data |
| Test infrastructure exceeding the code under test | Parameterized fixtures for 4 nearly-identical variants |
| Two systems for the same thing during a migration | Migration code outliving the migration |

## Adversarial mode (interactive grill)

The discipline test is only as good as the honesty of the answers. Most
overshoot lands because the answerer (often the same person proposing
the design) self-justifies. Run this skill as a counterparty — push
back on every typed field until the answer is concrete or the field
gets demoted.

**Auto-fail phrases.** When the justification for a typed field
contains any of these, the answer is *automatically* "use the simpler
form, demote a tier":

| Phrase | What it actually means | Verdict |
|---|---|---|
| "we might want this" / "we may need" | hypothetical | demote |
| "for future flexibility" / "future-proofing" | hypothetical | demote |
| "just in case" | hypothetical | demote |
| "for consistency" / "to match other variants" | uniform structure on non-uniform surface | demote |
| "easier to extend later" | premature abstraction | demote |
| "better DX" / "better ergonomics" | unnamed beneficiary | demote |
| "the lint requires it" / "clippy says" | opted-in pedant tax | suppress the lint, demote |
| "more correct" / "more rigorous" | aesthetics | demote |
| "in case the protocol changes" | wire-format hypothesis (valid for wire surfaces only — see *Tier C green-light*) | check the green-light boxes; otherwise demote |
| "we'll need it for telemetry" | name the dashboard, the metric, the alert | name them or demote |

**Adversarial questions to ask, one per typed field, in order:**

1. *Name the caller. Right now. File and line — or a downstream repo.*
2. *Is it pattern-matching, or just Display-formatting? If Display, why isn't it a `String`?*
3. *If you remove the field and use the simpler form, what specifically breaks?*
4. *You said "might want" / "for consistency" / "future" — that's a Hypothesis. Show me the evidence that promotes it to a Claim, or demote.*
5. *If this is here because of a lint, did you write the lint? If not, what stops you from suppressing it?*

**Stopping rule.** A field survives only if every answer is concrete:
named caller, named pattern-match site, named breakage, no hedging
words. Hedge → demote. Three hedges → drop the entire variant
structure and use a `String`.

This mode is essentially `/grill-me` applied to abstraction design.
For deeper interactive grilling, invoke `/grill-me` alongside this
skill on contested fields.

## Anti-patterns the skill catches

- *"We might want this someday"* → Tier C without evidence
- *"It's more correct"* → typed field without a consumer
- *"It's more consistent"* → uniform structure on a non-uniform surface
- *"Easier to extend"* → premature abstraction
- *"Better ergonomics"* → without naming who benefits
- *"The lint says so"* → the lint is enforcing something we chose to enforce

## When NOT to KISS (Tier C green-light)

The skill biases to A; sometimes C is correct. All three boxes must check:

- [ ] **Public/wire/persistence surface** with versioning cost (semver,
      protocol evolution, stored-data forward-compat)
- [ ] **≥ 2 named consumers** (not call sites — *organisations*, *teams*,
      or *external integrators*) **OR** one consumer + a documented
      evolution constraint
- [ ] **Reduction would force a breaking change later** (i.e. you can't
      cheaply walk it back if needed)

If any box is empty, B is the right tier. The checklist exists to give
architects an *affirmative path* to C (some designs deserve it) rather
than only a "don't" — but unchecked boxes are a flag, not a question.

Contexts where C-default is sometimes correct:
- Wire/persistence formats (cheap to add a field now, expensive after v1
  ships)
- Multi-team APIs where the consumer is named in an org chart
- Evolutionary protocols with explicit forward-compat requirements
- Published library APIs where breakage = consumer pain

For greenfield application code with a single team, A-default is correct
even on platforms.

## Output format

```
## Right-sizing: <thing>

**Goal**: <one sentence>

| Tier | Scope                                          | Cost  | Value | Verdict     |
|------|------------------------------------------------|------:|------:|-------------|
| A    | minimum that hits the goal                     |  1×   |  ~70% | …           |
| B    | A + structure for fields with named consumers  |  ~3–5×|  ~90% | recommended |
| C    | full structure, anticipated consumers          | ~10–20×|  100% | overshoots  |

(Cost as ratio over A — raw LoC doesn't transfer across languages or
project sizes; the curve does.)

**Recommendation**: Tier <X>, because <named consumer or absence thereof>.

**Specific overshoots** (if reviewing):
- `<field/variant/layer>` — fails the discipline test (no caller pattern-matches);
  reduce by <action>.

**Tier C check** (if recommending C):
- [ ] versioning cost? [ ] ≥2 consumers OR evolution constraint? [ ] breaking-change risk?
```

## Case study

See `references/case-study-error-types.md` for a worked example: a Rust
error-type design that started at Tier C (~+827 net LoC), got walked back
to Tier B (~+557 net LoC), and the trade-offs at each step. The same
analysis shape applies to non-Rust codebases.

## Related

- `rules/code-quality.md` — `@code-quality-pragmatist` for over-engineering
  review; this skill is the *prevention* counterpart to that *detection*.
- `rules/claims-vs-hypotheses.md` — the named-consumer test is a
  Claim/Hypothesis discipline applied to abstraction design.
- `@code-craftsman` — implements the chosen tier; bias toward A unless
  the briefing names a consumer.
