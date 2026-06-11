# Case Study: Error-Type Design (camus-ws PR #16)

A worked example of `/kiss` applied to error-type design. The
specifics are Rust, but the analysis shape — goal, tiers, discipline
test, overshoots — transfers to any language.

## Goal (as stated)

"Easier logging, debugging, and error reporting." Specifically: error
log lines should be correlatable to a specific connection (broker
address + reconnect epoch), and the Python binding should be able to
dispatch certain broker-side error codes to typed Python exception
classes.

## What shipped (Tier C)

The first cut introduced:

- A `ConnectionContext` struct with 7 fields (broker address, version,
  profile, instance ID, client version, client type, connection epoch).
- `Box<ConnectionContext>` on every structured error variant to satisfy
  `clippy::result_large_err` (a lint we had just opted into via
  pedantic).
- A `RegistrationRole { Publisher, Subscriber }` discriminator enum.
- A `QueryType { SequenceRange, TimestampRange, Asof }` enum carrying
  the original query parameters.
- Four structured error variants (`LogonFailed`, `RegistrationFailed`,
  `QueryFailed`, `PayloadTooLarge`) with named-field syntax and
  elaborate `#[error(...)]` Display templates.
- 186 LoC of parameterized test fixtures.

PR delta vs main: **+1 116 / −289 (+827 net)**.

## Applying the discipline test

> *Name a caller that will pattern-match on this field.*

| Field | Caller? |
|---|---|
| `LogonFailed.context.broker_version` | None — only Display formats it |
| `RegistrationFailed.role` | None — only Display formats it |
| `RegistrationFailed.siblings` | None — only Display formats it |
| `RegistrationFailed.status` | **Yes — `pyo3::to_py_err` could dispatch on it** |
| `QueryFailed.query_type` | None — caller already has the parameters |
| `QueryFailed.status` | **Yes — `pyo3::to_py_err` dispatches `PermissionError` to a typed Python exception** |
| `PayloadTooLarge.size, max` | None — operational decisions don't branch on these |
| `ConnectionContext.broker_address`, `connection_epoch` | None as fields, **but Display reads them** |

Almost everything fails the test. The two survivors are
`status` on `RegistrationFailed`/`QueryFailed`. The Display-driven uses
of `broker_address` and `connection_epoch` need the *values*, not typed
fields — a pre-formatted string suffices.

## What Tier A would have looked like

- One helper: `state.error_context_suffix() -> String` returning
  `"(broker=\"foo:8061\" epoch=3)"`.
- Existing `String`-payload variants (`LogonFailed(String)`,
  `RegistrationFailed(String)`, …) get the suffix appended at the
  error site.
- No new types. No `Box<>`. No discriminator enums. No fixture
  infrastructure.

Estimated cost: ~50 LoC. Captures the broker-correlation goal.
Misses the `pyo3` typed-dispatch goal.

## What Tier B (the chosen reduction) looks like

- The Tier A helper.
- `LogonFailed(String)` and `PayloadTooLarge(String)` stay tuple-shaped
  (no named consumer).
- `RegistrationFailed { topic, status, context: String }` and
  `QueryFailed { topic, status, context: String }` keep `topic` and
  `status` typed (named consumer: `pyo3::to_py_err`); everything else
  (role, siblings, query bounds) folds into `context: String` formatted
  once at the error site.

Estimated cost: ~250 LoC. Captures both goals.

PR delta after reduction: **+912 / −355 (+557 net)**, ~250 LoC lighter
than C.

## Tells that C overshot

1. **The discipline test fails for ~80% of the typed fields.** Every
   one of them was added on a "for consistency" or "for future use"
   basis.
2. **A same-week cleanup PR was needed** (#6 tuple→struct, #8 helper
   extraction, #9 doc note about Box deref, #10 cosmetic Display
   inconsistency). When the first cut needs four cleanup items in the
   same week, the design wasn't crisp.
3. **186 LoC of test fixtures for 4 nearly-identical variants.** The
   parameterized common-property tests verify what `thiserror`
   already derives. Diminishing returns past one example each.
4. **Box ceremony to satisfy a lint we opted into.**
   `clippy::result_large_err` only fires because we adopted `pedantic`.
   We chose the pedant; we paid the tax.

## Generalizable lessons

- **Goal-first.** "Easier logging" is two distinct goals
  (broker correlation + typed pyo3 dispatch). Each needs its own minimal
  intervention; conflating them encourages structuring everything.
- **Display-only consumers don't need typed fields.** A pre-formatted
  string carries the same operational value at a fraction of the cost.
- **The first programmatic consumer justifies its own field, not a
  pattern.** `status` doesn't justify `RegistrationRole`. They're
  independent design decisions.
- **Tests scale with code under test, not with code we wished we had.**
  186 LoC of fixtures for 4 variants → reduce both, not just the
  fixtures.
- **Lint-induced ceremony is recursive overshoot.** A pedantic lint
  pushed us to `Box<>`; we then wrote a CLAUDE.md note explaining the
  `Box<>`. Removing the structured fields removed both.

## What this looks like in other languages

- **Python**: A `dataclass` exception with 7 typed fields when callers
  only `str(exc)` it — make it `Exception(str)` with the context
  formatted in. Keep typed fields only where `isinstance` or attribute
  access drives behaviour.
- **TypeScript**: A discriminated union with 4 variants when only the
  `kind` field is switched on — collapse to a base interface with a
  `kind: string` and a `message: string`. Add a typed variant the
  moment the second consumer pattern-matches on a payload field.
- **Go**: A typed error struct with 5 fields when callers only call
  `.Error()` — keep `errors.New(fmt.Sprintf(...))`. Define a typed
  error only when `errors.As` or a sentinel pattern is used.
- **GraphQL**: A union type with multiple object members when the
  client only reads `__typename` and `message` — collapse to a single
  Error type with optional fields. Split when a client pattern-matches.

The skill is the same: name the consumer, scale the structure to the
consumer count, default to the smallest representation.
