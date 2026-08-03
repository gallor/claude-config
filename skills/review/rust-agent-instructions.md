# Rust-specific agent instructions

Injected into `@code-reviewer` for the `code` aspect when the diff contains `.rs` files (see `/review` SKILL.md step 5, language-aware agent selection). Append these to the agent's brief.

**Ownership and borrowing:**
- Flag any use of `.clone()` in a hot path or tight loop without justification — clones are rarely free
- Flag `Rc`/`RefCell` in code that could use `Arc`/`Mutex` (threading) or restructured ownership instead
- Check that lifetime annotations are correct and minimal — over-annotating is noise, under-annotating causes borrow errors the reviewer should have caught

**`unsafe` blocks:**
- Every `unsafe` block must have a comment explaining the safety invariant it relies on. Flag any that don't.
- Flag `transmute` unless the safety argument is airtight
- Flag raw pointer arithmetic without bounds reasoning

**Error handling:**
- `unwrap()` in non-test code is `[issue]` unless accompanied by a comment explaining why it can't fail. Skip `OnceLock::get().unwrap()` when the lock is demonstrably initialized earlier in the same scope or via `get_or_init` — the unwrap is justified by construction.
- `expect("message")` is preferred over bare `unwrap()`
- `panic!` in library code (non-binary) is `[issue]` — libraries should return `Result`

**Async:**
- Flag blocking calls (`std::thread::sleep`, sync I/O, `std::sync::Mutex::lock` in an async context) — use `tokio::time::sleep`, async I/O, `tokio::sync::Mutex` instead
- Flag `async` functions that do no actual async work (no `.await`) — they add overhead for nothing

**Static analysis integration:**
- `cargo clippy` findings are in `static-analysis.json` — do not re-report them, but use them as context
- Flag any `#[allow(clippy::...)]` suppressions without a justification comment

**FFI / PyO3 boundary (if present):**
- Panic across FFI is UB — any `unwrap()`/`expect()` that could panic in a function called from C/Python is `[critical]`
- Check GIL handling: `Python::with_gil` should be held for the minimum scope needed
