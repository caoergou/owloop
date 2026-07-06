# Feature: feat: per-session worktree branches to avoid same-day run pollution

## Priority: 3

## Requirements

- Change `OwloopEngine.setup_worktree()` so every `OwloopEngine.run()` invocation receives a unique session identifier instead of reusing the same `owloop/YYYYMMDD` branch and worktree path.
- Derive branch and worktree names from the session id, e.g. `owloop/<date>-<short-hash>`, so multiple runs on the same day cannot pollute each other's state.
- Persist the current session id and its branch/worktree path under `.owloop/logs/` so a later `--resume` invocation can locate and re-enter the previous session's branch.
- Add a `--resume` flag to `owloop run` and `owloop go` that reuses the most recent session's branch and worktree instead of creating a new one.
- Preserve the existing default behavior when `--resume` is not passed: create a fresh isolated worktree for every run.
- Add unit tests in `tests/test_engine.py` covering unique branch/worktree creation and `--resume` reuse.
- Document the manual command for cleaning up old owloop worktrees; do not implement automatic cleanup.

## Acceptance Criteria

- `uv run pytest tests/test_engine.py::test_setup_worktree_creates_unique_branch -q` → `1 passed`
- `uv run pytest tests/test_engine.py::test_setup_worktree_resume_reuses_latest -q` → `1 passed`
- `uv run pytest tests/test_engine.py -q` → all passed
- `uv run pytest tests/test_cli.py -q` → all passed
- `uv run owloop run --help | grep -q -- --resume && echo ok` → `ok`
- `grep -Rq 'git worktree remove' README.md .owloop/ 2>/dev/null && echo documented` → `documented`

## Exclusions

- Do not modify `pyproject.toml`, `uv.lock`, or any package manifest/version files.
- Do not change unrelated CLI commands (`init`, `spec`, `status`, `report`, `verify`, `issue`).
- Do not alter the adapter interface in `src/owloop/adapters.py` or existing agent adapters.
- Do not change the TUI rendering logic in `src/owloop/tui.py` except for any new event types needed by the engine.
- Do not modify unrelated tests such as `test_cli.py`, `test_adapters.py`, `test_tui.py`, etc.
- Do not add automatic cleanup or removal logic for previous owloop worktrees.

## Style

- Follow existing project conventions: type hints, `from __future__ import annotations`, dataclasses where appropriate, and ruff-compatible formatting.
- Match the existing `EngineConfig` / `OwloopEngine` patterns in `src/owloop/engine.py`.
- Use `subprocess.run` through `OwloopEngine._run_git` for all git operations.
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

- Current state: `OwloopEngine.setup_worktree()` names the branch `owloop/YYYYMMDD` and reuses the same worktree path on the same day; there is no `--resume` option; `RunSummary` has no session id.
- `uv run pytest tests/test_engine.py -q` currently passes on the existing suite.
- Target: unique branch/worktree per run, optional `--resume` reuse, no regressions.

Output when complete: `<promise>DONE</promise>`

<promise>DONE</promise>
