---
name: tdd
description: Spawn a TDD Feature Dev agent team — qa-sentinel writes failing tests, code-craftsman implements
user-invocable: true
argument-hint: <feature or bug description>
---

# TDD Feature Dev Team

Create an agent team to implement a feature or fix using test-driven development.

**Falsification-first.** The failing test is a counterexample to the current (non-)implementation. One counterexample drives the fix; don't pre-build verification breadth. See `rules/claims-vs-hypotheses.md` § Falsification First.

**Requirements**: $ARGUMENTS

## Workflow

1. **Create team**: `TeamCreate` with name `tdd-feature-dev`

2. **Create tasks**:
   - Task 1: "Write failing tests for: $ARGUMENTS" (assign to `test-writer`)
   - Task 2: "Implement until all tests pass" (assign to `implementer`, blocked by task 1)
   - Task 3: "Review implementation complexity" (blocked by task 2)
   - Task 4: "Verify test coverage and edge cases" (blocked by task 2)

3. **Spawn teammates**:
   - `test-writer` — `@qa-sentinel` with prompt: "Write failing tests for the following requirements: $ARGUMENTS. Follow `rules/python.md`. Cover happy paths, edge cases, and error scenarios. When tests are written, message `implementer` with: (1) what the tests cover, (2) the test file locations, (3) any design constraints implied by the test structure."
   - `implementer` — `@code-craftsman` with prompt: "Wait for `test-writer` to provide failing tests. Then implement the minimal code to make all tests pass. Run tests iteratively. Follow `rules/python.md`. When all tests are green, message the lead with a summary of what was implemented."

4. **Lead monitors** for task 1 completion. Once `test-writer` hands off to `implementer`, **shut down `test-writer`** (it's idle).

5. **Lead monitors** for task 2 completion. Once `implementer` finishes, **shut down `implementer`**.

6. **Parallel review** — spawn fresh teammates:
   - `complexity-reviewer` — `@code-quality-pragmatist` with prompt: "Review the implementation for over-engineering, unnecessary abstraction, and premature generalization. The goal was: $ARGUMENTS. Report findings to the lead."
   - `test-reviewer` — `@qa-sentinel` with prompt: "Review test coverage for the implementation. Check for missing edge cases, error scenarios, and boundary conditions. Report findings to the lead."

7. **Address findings** — lead coordinates any fixes. Shut down reviewers when done.

8. **Shut down team** (`TeamDelete`), then run `/review` once as a final gate

8. **Address review feedback** directly (do not re-enter `/tdd`), then invoke `/pr-pipeline`
