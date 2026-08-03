# Compat-specific agent instructions

Injected into the reviewer running the `compat` aspect (see `/review` SKILL.md step 5). Append these to the agent's brief. **Agent-neutral by design** — the compat check spans detection (a reviewer's job) and remediation (a test that the deprecation actually holds — a qa job), and `rules/code-quality.md` § Backwards Compatibility makes it an all-agents responsibility, so this lives in a supplement any reviewer can load rather than in one persona.

The compat aspect is **detection + blast-radius**: "this PR changed a public surface — does it break existing consumers, and if so is the break shimmed and tested?" Keep it terse and rubric-driven; it is not a place for deep design reasoning.

## 1. Detect the API-surface change

**Python (preferred): griffe** (deterministic, fast) diffs the public API and reports `ImportError`/`ModuleNotFoundError` per package; skipped packages are logged. This tool and its error classes are Python-specific. When griffe is unavailable (or the diff is Python), apply this fallback checklist against the diff:
1. **Removed exports** — symbols in `__all__` (or top-level) that no longer exist.
2. **Renamed** public functions/classes.
3. **Changed signatures** — removed parameters, changed types, required→optional or vice versa.
4. **New required parameters** on existing functions.
5. **Deleted files** that were importable.

**Non-Python (and the language-agnostic base): trace the changed public symbol with `rg`** per `directed-review.md` § "Tracing method: `rg` + read, not an LSP" — the same measured, ~0-FP, CI-reliable symbol-following that skill's caller-contract flavor uses (it even crosses FFI rename bridges an LSP can't). Do not add a new structural-analysis tool; `rg`-on-symbols already fills this need across the polyglot repos. griffe is the Python enrichment on top of that base, not a separate mechanism.

## 2. Blast-radius: external-consumer check (this is the high-value part)

Before escalating any API-change finding to `[issue]` or higher, verify the symbol has external consumers:

- Run `gh search code "{symbol}" --owner {org}` and filter out the current repo. Treat results as a **lower bound** — token access may not cover all repos, so no results means "no consumers found in accessible repos", not "definitely no consumers".
- **If consumers found:** escalate to `[issue]` or higher (a confirmed external consumer of a broken/removed symbol is `[critical]`).
- **If none found:** downgrade to `[suggestion]` with the note "no external consumers found in accessible repos."
- **Python pre-filter (run before searching):** underscored module (`_foo.py`) or underscored class → skip search, treat as internal. Symbol absent from `__all__` when `__all__` is defined → skip search, treat as internal. Only search symbols that pass this pre-filter.
- **Run all searches concurrently** — do not wait for one to complete before starting the next.

This is the check that catches cross-repo breakage a diff-local review can't see (e.g. a downstream repo's `CLAUDE.md`/config or code referencing a now-removed symbol; a config-schema change that crashes existing deployments on rollout).

## 3. Remediation must be shimmed AND tested (the qa bridge)

A public break is only *acceptably* handled when both hold (per `rules/code-quality.md` § Backwards Compatibility):
- **Shim present:** the removed/renamed symbol stays reachable via a deprecation path — the project's `@deprecated` decorator (e.g. `Core.utility.functions.deprecated`) if available, else `warnings.warn(DeprecationWarning)`; a replaced field kept as a `@property` + `@deprecated` delegating to the new name.
- **Shim tested:** a discriminating test proves the old path still works *and* emits the expected warning (`FutureWarning` for `@deprecated`, `DeprecationWarning` for raw `warnings.warn`). A shim with no test is a `[issue]` — "a test is only coverage if it can fail" (qa-sentinel): name the regression (someone deletes the shim) and confirm the test would go red.

Flag: an API break with a confirmed external consumer and **no** shim = `[critical]`; a shim with no test = `[issue]`; a break with no consumer found = `[suggestion]` (lower bound, not proof).

## Scope note

This aspect **detects and reviews** compat risk in a PR. It is **not** `@migration-specialist`, which plans *active* library migrations / version upgrades (msgpack→ormsgpack, Python 3.9→3.12) — a different, heavier task. If a PR is itself a large migration needing an audit + migration plan (not just a compat check), that is when `@migration-specialist` is the right tool.
