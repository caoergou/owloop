# Feature: feat: add session/resume semantics for interrupted overnight runs

**Status**: COMPLETE

## Priority: 3

## Requirements

- Introduce a unique session ID for every `owloop run` invocation (timestamp + short hash). The session ID must be deterministic enough to distinguish runs but does not need to be cryptographically unique.
- Persist per-session state under `.owloop/logs/` so an interrupted run can be resumed:
  - iteration count, tokens used, elapsed minutes, current spec (if any), and branch name.
  - session status (e.g., `running`, `interrupted`, `completed`).
- Add a `--resume` flag to `owloop run` that locates the most recent `interrupted` session, restores its counters/budgets, and continues from the spec that was active when the run was interrupted.
- When resuming, subtract previously consumed tokens and elapsed minutes from `max_tokens` and `max_duration` so the total budget stays consistent across the original and resumed sessions.
- Update `RunSummary` (and its JSON serialization) to include the session ID and resumed-from-session reference when applicable.
- Add or update unit tests in `tests/test_engine.py` covering:
  - session ID generation,
  - session state persistence on interruption,
  - budget carry-over on resume.

## Acceptance Criteria

- `uv run owloop run --help | grep -q -- --resume && echo ok` → `ok`
- `uv run pytest tests/test_engine.py -q` → all passed
- `uv run python -c "from owloop.engine import OwloopEngine; print('session_id' in dir(OwloopEngine))"` → `True` (or any deterministic API proving the engine exposes session identity)
- `uv run pytest tests/test_engine.py::test_session_state_persisted_on_interrupt -q` → all passed (test to be added; name is illustrative—actual test may differ)
- `uv run pytest tests/test_engine.py::test_resume_continues_token_and_duration_budget -q` → all passed (test to be added; name is illustrative)

## Exclusions

- Do not modify `pyproject.toml`, `uv.lock`, or any package manifest/version files.
- Do not change unrelated CLI commands (`init`, `spec`, `status`, `report`, `verify`, `issue`).
- Do not alter the adapter interface (`src/owloop/adapters.py`) or existing agent adapters.
- Do not change the TUI rendering logic in `src/owloop/tui.py` except for any new event types needed by the engine.
- Do not modify unrelated tests such as `test_cli.py`, `test_adapters.py`, `test_tui.py`, etc.
- Do not change the existing default behavior of `owloop run` when `--resume` is not passed.

## Style

- Follow existing project conventions: type hints, `from __future__ import annotations`, dataclasses where appropriate, and ruff-compatible formatting.
- Match the existing `EngineConfig` / `RunSummary` dataclass patterns in `src/owloop/engine.py`.
- Write pytest tests in the same style as `tests/test_engine.py` using `tmp_path`, `MockAdapter`, and subprocess-based git fixtures.
- Keep CLI option definitions consistent with the existing `@_common_run_options` decorator pattern in `src/owloop/cli.py`.

## Stuck Behavior

If you cannot make progress after 2 attempts at the same error, add a `## Blockers` section to this spec describing what's blocking you, commit your partial work, and output `<promise>DONE</promise>`.

## Verification

After each meaningful change, run:

- `uv run pytest tests/ -q`
- `uv run ruff check src/owloop tests`
- `uv run mypy src/owloop tests`

## Baseline

- Current state: `OwloopEngine.run()` always starts from a fresh state; `RunSummary` has no session ID; `owloop run` has no `--resume` option; interruption writes `owloop_summary_latest.json` with `stopped_reason: "interrupted"` but the next invocation resets counters.
- `uv run pytest tests/test_engine.py -q` currently passes on the existing suite.
- Target: add session/resume semantics without regressing existing tests.

Output when complete: `<promise>DONE</promise>`

<promise>DONE</promise>
