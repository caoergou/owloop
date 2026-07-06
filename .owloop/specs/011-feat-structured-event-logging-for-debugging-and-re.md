# Feature: structured event logging for debugging and reporting

## Priority: 3

## Requirements

- Add a structured, append-only JSON Lines event log at `.owloop/logs/events.jsonl`.
- Hook event persistence into `OwloopEngine._emit()` (or a dedicated wrapper) so every significant engine event is written to the log without changing existing `on_event` callback behavior.
- Each event line must be valid JSON containing `ts` (ISO-8601 timestamp), `session_id`, `kind`, and `data` fields.
- Persist the following engine event kinds at minimum: `iteration_start`, `iteration_end`, `agent_failed`, `agent_timeout`, `done_signal`, `no_done_signal`, `blocked`, `decide`, `verification_failed`, `verification_passed`, `max_tokens_reached`, `max_duration_reached`, `fix_loop_blocked`, `interrupted`.
- Create the log file lazily on first emitted event and append safely across iterations; reuse a stable `session_id` for the lifetime of the engine instance.
- Update `owloop report` to read `.owloop/logs/events.jsonl` and enrich the generated HTML with an event-driven section (e.g., iteration timeline, failure reasons, final stop reason).
- Add tests in `tests/test_engine.py` verifying file creation, line schema, and presence of expected event kinds.

## Acceptance Criteria

- `uv run pytest tests/test_engine.py::test_events_jsonl_created -q` → `1 passed`
- `uv run pytest tests/test_engine.py::test_events_jsonl_schema -q` → `1 passed`
- `uv run pytest tests/test_engine.py::test_events_jsonl_event_kinds -q` → `1 passed`
- `uv run pytest tests/test_engine.py::test_on_event_callback_still_fires -q` → `1 passed`
- `uv run pytest tests/test_report.py::test_report_includes_event_timeline -q` → `1 passed`
- `uv run pytest tests/test_engine.py tests/test_report.py -q` → `all passed`
- `uv run python -c "from owloop.engine import OwloopEngine; print('ok')"` → `ok`

## Exclusions

- Do not modify `pyproject.toml`, `uv.lock`, or add new runtime dependencies.
- Do not change existing CLI command signatures or behavior of `owloop run` / `owloop go`.
- Do not remove or alter existing `on_event` callback behavior; the new event logger must be additive.
- Do not modify unrelated tests in `tests/test_adapters.py`, `tests/test_cli.py`, `tests/test_brand.py`, `tests/test_learnings.py`, `tests/test_paths.py`, or `tests/test_promise.py`.
- Do not change the TUI rendering logic in `src/owloop/tui.py` or the console reporter formatting in `src/owloop/reporter.py` beyond what is strictly required for report integration.
- Do not break the existing `RunSummary` serialization format written to `logs/owloop_summary_latest.json`.

## Style

- Use `from __future__ import annotations` and type hints throughout new code.
- Follow ruff formatting and import sorting conventions.
- Use `pathlib.Path` for all file operations.
- Match existing engine patterns for `_emit`, dataclasses, and lazy initialization.
- Write pytest tests with `tmp_path` fixtures, descriptive names, and explicit assertions.

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

- `OwloopEngine._emit()` currently routes events only to `self.on_event`; no structured event log file exists.
- `logs/owloop_summary_latest.json` is the only run artifact consumed by `owloop report`.
- `uv run pytest tests/test_engine.py -q` currently passes (13 passed).

Output when complete:

<promise>DONE</promise>
