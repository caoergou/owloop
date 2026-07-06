# Feature: refactor: extract common streaming adapter base class to reduce Claude/Kimi duplication

**Status**: COMPLETE

## Priority: 3

## Requirements

- Extract a new abstract `StreamingAgentAdapter` base class in `src/owloop/adapters.py` that owns the subprocess lifecycle, stream reader thread, queue-based line streaming, promise signal extraction, token counting fallback, and timeout handling currently duplicated between `ClaudeCodeAdapter` and `KimiCodeAdapter`.
- `StreamingAgentAdapter` must extend `AgentAdapter` and declare abstract hooks `_build_cmd(self, prompt: str) -> list[str]` and `_parse_stream_event(self, raw: str) -> str | None` so concrete adapters only supply their CLI and stream format.
- Refactor `ClaudeCodeAdapter` to inherit from `StreamingAgentAdapter` and only implement `_build_cmd` and `_parse_stream_event` (plus its existing `preflight`, `__init__`, and `name`).
- Refactor `KimiCodeAdapter` to inherit from `StreamingAgentAdapter` and only implement `_build_cmd` and `_parse_stream_event` (plus its existing `preflight`, `__init__`, and `name`).
- Preserve all existing public behavior, signatures, and defaults of `ClaudeCodeAdapter`, `KimiCodeAdapter`, `AgentResult`, `AgentAdapter`, `MockAdapter`, and `get_adapter`.
- Add unit tests in `tests/test_adapters.py` that exercise `StreamingAgentAdapter` through a small mock concrete adapter, covering normal stream completion, promise signal extraction, timeout/idle behavior, and process cleanup.
- Improve line coverage for `src/owloop/adapters.py` compared to the pre-refactor baseline.

## Acceptance Criteria

- `uv run python -c "from owloop.adapters import StreamingAgentAdapter; print(StreamingAgentAdapter.__name__)"` → `StreamingAgentAdapter`.
- `uv run python -c "from owloop.adapters import StreamingAgentAdapter, ClaudeCodeAdapter, KimiCodeAdapter; assert issubclass(ClaudeCodeAdapter, StreamingAgentAdapter) and issubclass(KimiCodeAdapter, StreamingAgentAdapter); print('ok')"` → `ok`.
- `uv run python -c "from owloop.adapters import ClaudeCodeAdapter, KimiCodeAdapter; print(ClaudeCodeAdapter.__mro__); print(KimiCodeAdapter.__mro__)"` → both MROs contain `StreamingAgentAdapter`.
- `uv run pytest tests/test_adapters.py -q` → all passed.
- `uv run pytest tests/ -q` → all passed.
- `grep -q "class StreamingAgentAdapter" src/owloop/adapters.py && echo ok` → `ok`.
- `grep -q "class.*StreamingAgentAdapter" tests/test_adapters.py && echo ok` → `ok` (tests reference the base class).
- `uv run python -c "from owloop.adapters import ClaudeCodeAdapter, KimiCodeAdapter; c = ClaudeCodeAdapter(); print(c._build_cmd()); k = KimiCodeAdapter(); print(k._build_cmd('hi'))"` → prints the claude and kimi command lists unchanged from baseline.

## Exclusions

- Do not modify `pyproject.toml` or `uv.lock`.
- Do not change unrelated adapters (`MockAdapter`, `AgentAdapter` base interface, `get_adapter`) except for any import-order impacts required by the refactor.
- Do not change unrelated tests outside `tests/test_adapters.py`.
- Do not break existing CLI commands or engine behavior (`uv run owloop --help`, `uv run owloop go --help`, `uv run owloop check`).
- Do not introduce new runtime dependencies.

## Style

- Follow existing project conventions: Python 3.10+ type hints, `from __future__ import annotations`, ruff formatting, and pytest patterns already used in `tests/test_adapters.py`.
- Keep the base class API minimal and focused on streaming subprocesses; avoid speculative generality for agents not yet implemented.
- Preserve existing docstring style and inline comments where behavior is subtle (e.g., process-group teardown, `DEFAULT_IDLE_TIMEOUT` rationale).

## Stuck Behavior

If you cannot make progress after 2 attempts at the same error, add a `## Blockers` section to this spec describing what's blocking you, commit your partial work, and output `<promise>DONE</promise>`.

## Verification

Run these exact commands after each change, before claiming completion:

```bash
uv run pytest tests/ -q
uv run ruff check src/owloop tests
uv run mypy src/owloop tests
```

## Baseline

- `tests/test_adapters.py` currently tests `ClaudeCodeAdapter._build_cmd`, `KimiCodeAdapter._build_cmd`, and `MockAdapter` behavior; all tests pass.
- `StreamingAgentAdapter` does not exist yet; common streaming logic is duplicated in `ClaudeCodeAdapter` and `KimiCodeAdapter`.
- No dedicated unit tests exist for the shared streaming subprocess lifecycle.

Output when complete: <promise>DONE</promise>
