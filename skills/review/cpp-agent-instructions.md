# C++-specific agent instructions

Injected into `@code-reviewer` for the `code` aspect when the diff contains `.cpp`/`.hpp`/`.h` files (see `/review` SKILL.md step 5, language-aware agent selection). Append these to the agent's brief. Calibrated for long-lived production codebases (trading, infra, libraries) where a regression is expensive and "good style" is judged by what the compiler emits, not the textbook.

**Stance (this is the C++-specific judgment, beyond the generic reviewer's):**
- Default to **no change** unless the diff justifies it; question scope on every PR.
- Push breaking changes to the **next minor** — don't change behavior under existing users on the current release branch.
- Review performance at the **call site, for what the compiler actually emits**, not in the abstract.
- **Approve with caveats** when the principal change is sound but minor things are off — don't block on nits.

**Reference docs (read before reviewing chip C++ — chip diverges from generic C++ idioms; prefer chip's rules):**
- `~/.claude/chip-cpp-rules.pdf` — mechanical clang-format rules (braces, indentation, west-const, namespace style); pass-0 basis.
- `~/.claude/Chip Development Best Practices_*.pdf` — PR procedures, modern C++ idioms, class design, optimization, headers, casting, common bugs, chip utilities (`Core::FixedVector`, `CORE_ASSERT`, `Core::DenseHashMap`, `Core::LogNoCopy`).
- `[[reference-chip-cpp-guidelines]]` (distilled rules), `[[feedback-chip-cpp-review-bias]]` (known reviewer pitfalls).

**Line-number staleness gotcha:** GitHub inline-comment `line`/`original_line` anchor to the revision the comment was posted against, not current HEAD — after a squash/rebase they're stale. To audit "is this addressed?", read the current file and grep for the *substance* of the comment, not its location.

Run these passes in order; stop after the first that finds blocking issues and let the author address them before continuing.

**0. Local style (new files only — modified files carry their own history):** check against `chip-cpp-rules.pdf`. `#pragma once` (infer from adjacent files); `namespace Foo {` opening brace same line, body *not* indented; struct/class brace on a *new* line; **no** column-alignment padding on declarations; 160-char lines; don't declare `= default` for trivially-generated specials; west-const (`const int`); keep unused-param names; `using` not `typedef`; `explicit` on unary ctors unless implicit conversion intended.

**1. Backward compatibility & rollout pacing:** wire-format field add/remove/reorder (are old peers tolerant?); default-behavior flips (keep old default, add opt-in for new); ABI/API on public headers — renamed params, removed methods, virtual signature changes demand a deprecation shim; risky changes target the *next* minor not the current; any consumer-visible change needs a release note naming the changed field/flag/symbol.

**2. Performance — at the call site:** register spill (an added struct/out-param pushing hot vars to the stack); tail calls (a delegating call should stay one — a wrapper turning into a frame needs a why); inlining (many-call-site small accessors that aren't inlined — ask for `inline` or check the binary); `std::optional<vector<T>>`/`std::optional<Container>` returns holding a heap allocation on a hot path (prefer `const T*` when the source owns); per-call allocations on register paths (`Core::String` ctors, vector copies, `std::function` captures in tight loops); `opt.value()` adds an exception path — prefer `*opt` / pointer-style access; pointer-chase "optimizations" that just hide the same indirections (a wash); fast-path complexity that exploits a race-window windfall (keep the fast path simple); hot vs warmup log parity.

**3. API hygiene:** default args on virtuals (every override must consider them — drop or document); single-arg overloads shadowing the real multi-arg API (remove or `private`); public/private split ("who may call this?" → `private` + rewrite the comment from that view); predicate naming `IsX`/`HasX`/`ShouldX`, not `GetX()` returning `bool`; return-type leak (`unique_ptr<Impl>` from a public header forces the impl into every TU — prefer interface+factory); friend decls signalling a wrong boundary; **argument-order consistency** across a callback/interface family (a new sibling should match `(context, exchMessage)` order); pass the externally-facing "real" object to callbacks, not an internal wrapper; **state-before-gate ordering** — state the rejection path needs must be set *before* a gating predicate (`CanSend()`), or the reject runs with stale state.

**4. Const-correctness:** `const`-qualify non-mutating members (esp. after a refactor moves work out); `const auto&` locals where feasible; `noexcept` on dtors/moves/swap/hash (document if not).

**5. Document the non-obvious (why/who/which, not what):** which union/variant member to read (document the discriminator); an invariant enforced elsewhere that a future edit could break; a workaround for a specific bug/platform; a default that's a deliberate compat choice; non-trivial lifetime ("owned by X, valid until Y"). Skip when the name/type already says it or RAII makes it obvious.

**6. Safe defaults:** a new value-type field should default to a state meaning "not set" (e.g. `INVALID_POLICY`), not to the most-common value.

**6a. Boundary inputs on new/changed *public* signatures:** for each parameter, check the degenerate values the *type* admits (`0`/negative counts, empty containers/`string_view`, permitted null) and trace whether the body misbehaves (infinite loop, UB, div-by-zero, `operator[]` OOB). **A boundary value that only today's in-tree caller avoids still needs a guard** — a public signature lets any future/external caller pass it. "The one caller passes N>0" is not a type-enforced contract.

**7. Scope discipline:** a PR does one thing; question drive-by changes unmotivated by the principal change (separate commits fine, bundled = review noise).

**8. Hot/warmup path symmetry:** startup/warmup and hot paths should agree on what's logged and at what verbosity — operators watch warmup output too.

**9. Fix legitimacy (bug-fix PRs — extra scrutiny; a plausible fix can be wrong differently than the bug):** demand a **symptom statement** (the observed failure that motivated it — without it you can't judge sufficiency); check **you didn't just move the problem** (a tight loop moved "to the dispatcher" is still a tight loop — a blocking dispatcher pegs the CPU); confirm the **precondition actually holds** (is this path really called before X? is `_server.fd()` the socket fd or the epoll fd?); prefer a **simpler existing primitive** (`Core::TcpAcceptor` over hand-rolled `bind`+`listen`+`fcntl`); the **fix must exercise the bug** (a regression test that fails without it, or describe one). First question on a fix PR: *"what caused this?"*

**10. Generalize before approving:** a fix at one site — evaluate it against siblings. Push a subclass fix down to the common base (`SocGenFixOrderActions` → `BaseOrderAdapterImpl`); walk sibling callers (`OnOrder` → `OnMassCancel`, `OnContractAction`); audit severity/log-level parity across mirror error paths.

**11. State-machine reasoning (status enums, queue/dequeue, connect/disconnect — review invariants, not lines):** enumerate the invariants explicitly and check the diff preserves each; **default safe stance** — what happens on `UNKNOWN`/unset? if the default is permissive, *failing to detect* is a permissive failure; **asymmetric importance** — `CLOSED` matters more than `OPEN` when the default is permissive (failing to detect OPEN just delays trading; failing to detect CLOSED keeps trading after halt — don't add OPEN detection if CLOSED isn't reliable); when a new state is added, walk every gate branching on the old states and decide its behavior for the new one (default fall-through to permissive is usually wrong).

**Anti-patterns to flag:** `std::function` capturing large lambdas by value in hot paths; `std::optional<Container>` returns where the heap alloc dominates; unbounded caches (insert-only `unordered_map`); `find` then `emplace` on the same key (use `try_emplace`); default-arg `nullptr` on a virtual; virtuals on a hot path where CRTP/free function would do; `const&` to a member captured in a lambda outliving the call; error-swallowing catch blocks without confirming callers expect it.

**Praise the right moves, terse:** "yay, tail call." / "nice — right primitive." / "good catch on the discriminator comment."

**Load-bearing claims need evidence (per Claims vs Hypotheses):** when an author justifies behavior with kernel/syscall/compiler claims ("the kernel doesn't spuriously short-write on non-blocking sockets", "the compiler will inline this"), demand the citation/measurement/known case when the claim is load-bearing for the change — don't accept "I'm pretty sure".
