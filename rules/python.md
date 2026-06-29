# Python Conventions

## Environment

- Use micromamba to manage conda environments: `micromamba run -n $CONDA_ENV <command>`
  - Default environment: `chippy-dev`

## Formatting (ruff)

- Use `ruff format` style **only for changed lines**, not entire files, unless:
  - The user explicitly asks to format the whole file
  - You are creating a new file

## Assertions

- **Never use `assert` statements in production code** (non-`test_*.py` files). They add hot-path branching, are stripped by `python -O`, and validate internal invariants that callers already guarantee. Trust internal code; only validate at system boundaries with proper exceptions.
- `assert` is fine in test files (`test_*.py`).

## Testing (pytest)

### Philosophy: test properties, not examples

Exact-value assertions (`assert f(3) == 9`) are fragile and incomplete. Prefer asserting **properties that hold for all valid inputs**. Use `hypothesis` for property-based tests where applicable:

```python
# Weak: tests one example, manually computed
def test_concatenate():
    assert concatenate("abc", "def") == "abcdef"

# Better: parametrized examples cover corners, but still finite
@pytest.mark.parametrize("left, right, expected", [
    ("a", "b", "ab"),
    ("", "", ""),
    ("", "b", "b"),
])
def test_concatenate(left, right, expected):
    assert concatenate(left, right) == expected

# Best: properties hold for ALL inputs — hypothesis finds the edge cases
from hypothesis import given, strategies as st

@given(left=st.text(), right=st.text())
def test_concatenate_properties(left, right):
    result = concatenate(left, right)
    assert result.startswith(left)
    assert result.endswith(right)
    assert len(result) == len(left) + len(right)
```

Not every function has clean properties. Use exact-value tests for lookups, config parsing, and protocol conformance. Use property-based tests for transformations, serialization round-trips, and invariants.

### Style

- **Prefer function-style tests over class-based tests**
  ```python
  # Good
  def test_user_can_login():
      ...

  # Avoid
  class TestUserLogin:
      def test_can_login(self):
          ...
  ```

- **Parameterize tests when possible** - Use `@pytest.mark.parametrize` for multiple inputs when testing exact values

- **Prefer fixtures over decorator constants for shared test dimensions** - Use `@pytest.fixture(params=[...])` instead of a module-level `pytest.mark.parametrize` constant. Tests that need the dimension request the fixture; tests that don't are unaffected. Adding a new variant requires updating one fixture, not hunting for decorators across test files. For stateless fixtures used with `hypothesis` (e.g., serialization backends), use `scope="module"` to avoid the `HealthCheck.function_scoped_fixture` warning without needing `suppress_health_check`.

- **Prefer `create_autospec` over `MagicMock(spec=...)`** - `create_autospec(Cls, instance=True)` enforces both attribute names and method signatures. `MagicMock(spec=Cls)` only checks attribute names; wrong-arity calls pass silently. Unspec'd `MagicMock()` is worst: accessing non-existent attributes returns new mocks instead of raising `AttributeError`, hiding integration bugs.

- **Mock I/O should respect size arguments** - When mocking `read(n)`, `recv(n)`, or similar, cap the return at `n` bytes (`return data[:n]`) to match real I/O semantics. Returning more than requested can mask buffer overread bugs.

- **When deleting a test file, check conftest.py for orphaned fixtures** - Fixtures defined in `conftest.py` that were only consumed by the deleted file become dead code. Grep for fixture names across remaining `test_*.py` files before considering the deletion complete.

- **Prefer `asyncio.Runner` for sync benchmark functions that call coroutines** - `with asyncio.Runner() as runner: runner.run(coro)` is cleaner than manual `asyncio.new_event_loop()` / `loop.close()` and avoids the deprecated pytest-asyncio `event_loop` fixture override. Not a hard rule; depends on pytest-asyncio version and project conventions.

## Performance

- **Prefer `itertools.starmap` over `map` with multiple iterables.** `map(f, a, b, c)` builds a new argument tuple per call from each iterable. `starmap(f, zip(a, b, c))` passes zip's pre-built tuple directly as `*args`, avoiding the redundant tuple allocation. ~10% faster at scale (measured at 13k items with dataclass construction). Also faster than list comprehensions with tuple unpacking, which add `UNPACK_SEQUENCE` + `STORE_FAST`/`LOAD_FAST` bytecode overhead per iteration.
