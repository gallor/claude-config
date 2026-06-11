# Execution Efficiency

Two principles that prevent most wasted tool calls and token burn.

---

## 1. Find the cheapest verification before committing

Before investing >10 minutes in any approach, spend 2 minutes finding the
minimal check that would falsify it.

- Tool doesn't exist or doesn't support the environment → pivot immediately
- Test breaks → fix before continuing
- Approach requires a dependency → confirm it's present first

The instinct to suppress is: "this will probably work, I'll find out as I go."
That instinct is expensive. A failing `tool --version` or a one-line smoke test
costs nothing; discovering the dead end after 30 minutes costs everything.

This is the same principle as `rules/claims-vs-hypotheses.md` applied to
tooling and approaches rather than technical claims.

## 2. Identify every independent enforcement point for the property being fixed

Components don't always form a linear stack. A property can be enforced at
multiple independent points in the dependency graph — fixing one doesn't fix
the others.

Ask: **"If only this fix exists, can the bug still occur?"**

If yes, there's another enforcement point. Find it before shipping.

The conflated queue was an example: the Rust `watch` channel bounds the queue
at the Rust→Python handoff; the Python `deque(maxlen=1)` bounds it at the
drain→callback handoff. Neither depends on the other. Both are independently
necessary. "Check all layers" misses this because it implies a traversal of a
dependency chain — but these are parallel enforcement points, not layered ones.

The dependency structure matters:
- **Chain** (A → B → C): a fix at A propagates to B and C automatically; verify
  at C that it did.
- **Independent enforcement** (A and B both enforce property P): fixing A
  doesn't fix B; both need independent fixes.
- **Feedback** (A affects B, B affects A): fixing one side can break the
  invariant at the other; verify the round-trip.

---

**For agents specifically:** exploratory work ("run this and see what happens")
belongs in the main session, not in a subagent. Agents add latency and
require precise briefs. Use them for well-defined parallelizable work with a
clear deliverable.
