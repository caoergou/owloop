# Feature: feat: real-time token tracking with per-iteration budget cap

**Status**: COMPLETE

## Priority: 3

## Requirements

- Extend `TokenTracker` so adapters can feed real usage values as they stream, while still falling back to the existing regex/heuristic when no explicit usage is emitted.
- Update `ClaudeCodeAdapter` to parse `result` stream events and immediately update `TokenTracker` with their `usage` / `total_cost_usd` fields instead of waiting until the iteration ends.
- Update `KimiCodeAdapter` to detect usage metadata in its stream events when the Kimi CLI exposes it; fall back to the character-count heuristic when it does not.
- Add a `max_tokens_per_iteration` field to `EngineConfig` and a `--max-tokens-per-iteration` CLI option for `owloop run` (reuse the existing `MaxTokensParamType` parser so shorthand like `10k` works).
- Enforce the per-iteration cap inside `OwloopEngine.run_iteration()` by terminating the adapter early when the running token count for that iteration exceeds the limit.
- Surface accumulated token usage and estimated cost in `RunSummary`, the HTML report, and the TUI status bar.
- Add focused unit tests in `tests/test_tokens.py`, `tests/test_adapters.py`, and `tests/test_cli.py` that exercise real-time updates, the per-iteration kill, and the new CLI option.

## Acceptance Criteria

- [x] `uv run pytest tests/test_adapters.py::test_claude_adapter_updates_token_tracker_from_stream -q` → all passed.
- [x] `uv run pytest tests/test_adapters.py::test_kimi_adapter_extracts_usage_or_falls_back_to_heuristic -q` → all passed.
- [x] `uv run owloop run --help | grep -q -- --max-tokens-per-iteration && echo ok` → `ok`.
- [x] `uv run pytest tests/test_cli.py::test_run_parses_max_tokens_per_iteration -q` → all passed.
- [x] `uv run pytest tests/test_tokens.py::test_engine_kills_iteration_exceeding_per_iteration_cap -q` → all passed.
- [x] `uv run pytest tests/test_tokens.py::test_run_summary_includes_estimated_cost -q` → all passed.
- [x] `uv run pytest tests/test_report.py tests/test_tui.py -q` → all passed.
- [x] `uv run pytest tests/test_tokens.py tests/test_adapters.py tests/test_cli.py -q` → all passed.

## Exclusions

- Do not modify `pyproject.toml`, `uv.lock`, or the package manifest.
- Do not change unrelated CLI commands (`go`, `spec`, `init`, `status`, `report`, `discover`, `version`, `check`).
- Do not remove the existing `max_tokens` cross-iteration budget or the `--max-tokens` option.
- Do not change unrelated tests in `tests/test_engine.py`, `tests/test_subagents.py`, `tests/test_reporter.py`, or any other test file outside the ones named in Acceptance Criteria.
- Do not introduce new external dependencies; use only the standard library and packages already declared.

## Style

- Add type hints for all new functions and dataclass fields.
- Follow the existing ruff/pytest configuration in `pyproject.toml`.
- Match the existing test patterns: use `CliRunner` for CLI tests, `MockAdapter`/`AgentResult` for engine tests, and `tmp_path` with a real git repo when the engine needs one.
- Keep changes minimal and scoped to `src/owloop/tokens.py`, `src/owloop/adapters.py`, `src/owloop/engine.py`, `src/owloop/cli.py`, `src/owloop/report.py`, and `src/owloop/tui.py`.

## Verification

After every meaningful change, run:

```bash
uv run pytest tests/ -q
uv run ruff check src/owloop tests
uv run mypy src/owloop tests
```

All three must pass before claiming completion.

## Baseline

- `uv run owloop run --help | grep -q -- --max-tokens-per-iteration` currently exits 1 (option missing).
- `EngineConfig` currently has `max_tokens` but no `max_tokens_per_iteration` field.
- `uv run pytest tests/ -q` currently reports 188 passed.
- Target: per-iteration token cap implemented, real-time usage tracking wired for both adapters, cost surfaced in report/TUI, and the full test suite remains green.

Output when complete:

<promise>DONE</promise>
