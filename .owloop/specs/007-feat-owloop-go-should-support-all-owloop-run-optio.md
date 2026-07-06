# Feature: feat: owloop go should support all owloop run options

**Status**: COMPLETE

## Priority: 3

## Requirements

- [x] Extend the `go` command so it accepts the same runtime options as `run`: `--agent`, `--model`, `--verifier-model`, `--subagents`, `--idle-timeout`, `--max-duration`, `--max-tokens`, and `--worktree/--no-worktree`.
- [x] Forward every parsed option from `go` into the engine runner, replacing the currently hard-coded defaults (`agent="claude"`, `worktree=True`, `idle_timeout=3600`, `max_duration=0`, `max_tokens=0`, no verifier, no subagents).
- [x] Keep `go` unlimited by design; do not expose the `--max-iterations` option that `run` uses.
- [x] Preserve current defaults when options are omitted: agent=claude, worktree enabled, idle_timeout=3600s, max_duration=0, max_tokens=0, verifier_model=None, subagents=False.
- [x] Add unit tests that verify the help text exposes the new options and that parsed option values are forwarded correctly to the engine runner.

## Acceptance Criteria

- [x] `uv run owloop go --help | grep -q -- --agent && echo ok` → `ok`
- [x] `uv run owloop go --help | grep -q -- --max-tokens && echo ok` → `ok`
- [x] `uv run owloop go --help | grep -q -- --max-duration && echo ok` → `ok`
- [x] `uv run owloop go --help | grep -q -- --subagents && echo ok` → `ok`
- [x] `uv run owloop go --help | grep -q -- --verifier-model && echo ok` → `ok`
- [x] `uv run owloop go --help | grep -q -- --worktree && echo ok` → `ok`
- [x] `uv run pytest tests/test_cli.py -q` → all passed.
- [x] `uv run pytest tests/ -q` → all passed.

## Exclusions

- Do not modify `pyproject.toml` or `uv.lock`.
- Do not change the `run` command or the shared run-option decorator.
- Do not alter the engine layer, adapter internals, or unrelated CLI commands (`init`, `spec`, `report`, `status`, `version`).
- Do not modify test files other than those required for the new CLI tests.
- Do not change README.md or other documentation files.

## Style

- Follow existing Click decorator ordering and Python type hints in the CLI module.
- Use `CliRunner` and `unittest.mock.patch` patterns already established in the test suite.
- Keep ruff and mypy clean; match the project line-length and docstring conventions.

## Stuck Behavior

If you cannot make progress after 2 attempts at the same error, add a `## Blockers` section to this spec describing what's blocking you, commit your partial work, and output `<promise>DONE</promise>`.

## Verification

- `uv run pytest tests/ -q`
- `uv run ruff check src/owloop tests`
- `uv run mypy src/owloop tests`

## Baseline

- `owloop go --help` currently exposes only `--model`.
- `owloop run --help` exposes all runtime options via the shared decorator.
- `tests/test_cli.py` currently passes.
- Target: `owloop go --help` mirrors `owloop run --help` options except `--max-iterations`.

Output when complete: `<promise>DONE</promise>`

<promise>DONE</promise>
