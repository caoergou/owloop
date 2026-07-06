# Feature: feat: add dry-run / one-shot mode to validate specs without burning tokens

**Status**: COMPLETE

## Priority: 3

## Requirements
- Add a `--dry-run` / `--one-shot` flag to the `owloop run` command in `src/owloop/cli.py`.
- When the flag is set, `OwloopEngine` runs exactly one agent iteration and stops.
- In dry-run mode the engine must not push to the remote and must not leave committed changes in the active worktree.
- Preflight checks (`preflight_check`) and spec checks (`_spec_status`) must still execute normally.
- After the single iteration, output a concise pass/fail report that includes:
  - whether the agent emitted `<promise>DONE</promise>`;
  - the number of acceptance criteria that passed versus failed;
  - total tokens used in the iteration.
- Surface the dry-run option in `EngineConfig` so tests can drive it directly.
- Add unit tests in `tests/test_engine.py` and CLI tests in `tests/test_cli.py`.

## Acceptance Criteria
- [ ] `uv run owloop run --help | grep -Eq -- '--dry-run|--one-shot' && echo ok` → `ok`
- [ ] `uv run pytest tests/test_cli.py -k dry_run -q` → all passed
- [ ] `uv run pytest tests/test_engine.py -k dry_run -q` → all passed
- [ ] `uv run python -c "from owloop.engine import EngineConfig; c = EngineConfig(project_dir='.', dry_run=True); print(c.dry_run)"` → `True`
- [ ] `uv run pytest tests/test_cli.py tests/test_engine.py -q` → all passed
- [ ] `uv run ruff check src/owloop tests` → no errors
- [ ] `uv run mypy src/owloop tests` → no errors

## Exclusions
- Do NOT modify `pyproject.toml`, `uv.lock`, or `README.md`.
- Do NOT change the existing `--dry-run` behavior of `owloop spec-from-issue`.
- Do NOT modify, delete, or comment out existing tests in `tests/test_cli.py` or `tests/test_engine.py`.
- Do NOT alter existing CLI commands (`go`, `init`, `spec`, `status`, `report`, `check`, `version`, `discover`, `spec-from-issue`).
- Do NOT change the default behavior of `owloop run` when `--dry-run` is omitted.
- Do NOT refactor the TUI or reporter implementations beyond what is needed to display the dry-run report.

## Style
- Use Python type hints and dataclass fields consistent with `EngineConfig` in `src/owloop/engine.py`.
- Follow the Click option patterns already used for `_common_run_options` in `src/owloop/cli.py`.
- Keep the new flag name consistent with the existing `--dry-run` convention in `src/owloop/cli.py`.
- Match the existing pytest style in `tests/test_engine.py` and `tests/test_cli.py`.

## Stuck Behavior
If you cannot make progress after 2 attempts at the same error, add a `## Blockers` section to this spec describing what's blocking you, commit your partial work, and output `<promise>DONE</promise>`.

## Verification
- `uv run pytest tests/ -q`
- `uv run ruff check src/owloop tests`
- `uv run mypy src/owloop tests`

## Baseline
- `owloop run --help` currently shows no `--dry-run` or `--one-shot` option.
- `EngineConfig` currently has no `dry_run` field.
- `OwloopEngine.run()` always pushes after a successful iteration.
- `uv run pytest tests/test_cli.py tests/test_engine.py -q` currently passes.

Output when complete:

<promise>DONE</promise>
