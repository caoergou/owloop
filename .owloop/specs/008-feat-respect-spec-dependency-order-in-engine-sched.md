# Feature: feat: respect spec dependency order in engine scheduling

## Priority: 3

## Requirements

- Extend `src/owloop/spec_queue.py` to read the `## Depends On` section from every spec (treat missing, empty, or "none" as no dependencies).
- Build a dependency graph over incomplete specs keyed by spec filename references in `## Depends On`.
- Implement topological selection so the engine always picks the highest-priority incomplete spec whose dependencies are already complete.
- Preserve the existing tie-breaker: when multiple specs are dependency-ready, pick the one with the lower priority number, then lexicographically earlier filename.
- Add cycle detection in `src/owloop/spec_linter.py` so `owloop check` reports a clear error if the dependency graph contains a cycle.
- Update `src/owloop/engine.py` to use the new dependency-aware selection instead of raw filename order.
- Add unit tests in `tests/test_spec_queue.py` covering dependency parsing, topological ordering, cycles, missing dependencies, and fallback behavior.

## Acceptance Criteria

- `uv run pytest tests/test_spec_queue.py -q` → `passed`.
- `uv run pytest tests/test_spec_linter.py::test_circular_spec_dependency_fails -q` → `passed`.
- `uv run pytest tests/test_engine.py::test_engine_picks_dependency_ready_spec -q` → `passed`.
- `uv run owloop check --strict` → exits `0` and output contains `0 errors`.

## Exclusions

- Do NOT modify `pyproject.toml` or `uv.lock`.
- Do NOT change unrelated CLI commands or their existing option defaults.
- Do NOT alter the spec status convention (`Status: COMPLETE`, `**Status**: COMPLETE`, `## Status: COMPLETE`).
- Do NOT delete or weaken existing `spec_queue.py` helpers (`get_root_specs`, `is_root_spec_complete`, `get_incomplete_root_specs`, `count_root_specs`, `count_incomplete_root_specs`, `find_next_spec_number`).
- Do NOT modify unrelated tests in `tests/`.

## Style

- Follow existing `src/owloop/spec_queue.py` typing conventions (Python 3.10+ union syntax, `pathlib.Path`).
- Match `src/owloop/spec_linter.py` patterns for dataclass findings and section parsing.
- Use `pytest` fixtures and `tmp_path` for file-based tests, consistent with `tests/test_spec_linter.py`.
- Keep functions small, pure, and well-typed; run `ruff` and `mypy` clean.

## Stuck Behavior

If you cannot make progress after 2 attempts at the same error, add a `## Blockers`
section to this spec describing what's blocking you, commit your partial work, and
output `<promise>DONE</promise>`.

## Verification

```bash
uv run pytest tests/ -q
uv run ruff check src/owloop tests
uv run mypy src/owloop tests
```

## Baseline

- `uv run owloop check --strict` currently reports Requirements section is empty and missing shell commands in Acceptance Criteria for this spec.
- `src/owloop/spec_queue.py` currently picks the first incomplete spec by filename only (`get_first_incomplete_root_spec`).
- No `tests/test_spec_queue.py` exists.
- `uv run pytest tests/ -q` currently passes.

Output when complete:

<promise>DONE</promise>
