# Feature: feat: make TUI optional with --no-tui / --plain flag

## Priority: 3

## Requirements
- Add a `--no-tui` / `--plain` boolean flag to the `owloop run` command surface and propagate it through `_common_run_options` / `_run_engine` in `src/owloop/cli.py`.
- When the flag is set, bypass `OwloopTUI` and route engine events to `ConsoleReporter` even if stdout is a TTY.
- Preserve interactive confirm prompts (`confirm_dirty`, `confirm_worktree`) in plain mode using a standard `Console` instead of the TUI console.
- Keep the existing TTY-based TUI selection as the default when the flag is absent.
- Add focused unit tests in `tests/test_cli.py` that verify the flag is accepted, forces the `ConsoleReporter` path, and does not break interactive prompts.
- Update `README.md` and `CLAUDE.md` to document the new `--no-tui` / `--plain` option.

## Acceptance Criteria
- [ ] `uv run owloop run --help | grep -q -- --no-tui && echo ok` → `ok`
- [ ] `uv run owloop run --help | grep -q -- --plain && echo ok` → `ok`
- [ ] `uv run python -c "from click.testing import CliRunner; from owloop.cli import main; r = CliRunner().invoke(main, ['run', '--no-tui']); print('no such option' not in r.output.lower())"` → `True`
- [ ] `uv run pytest tests/test_cli.py -k "no_tui or plain" -q` → all passed
- [ ] `uv run pytest tests/test_cli.py -q` → all passed
- [ ] `grep -q -- --no-tui README.md && echo ok` → `ok`
- [ ] `grep -q -- --plain CLAUDE.md && echo ok` → `ok`

## Exclusions
- Do NOT modify `pyproject.toml`, `uv.lock`, or `.gitignore`.
- Do NOT modify unrelated CLI commands (`init`, `status`, `report`, `spec`, `go`, `check`, `discover`, `version`).
- Do NOT modify unrelated tests outside `tests/test_cli.py`.
- Do NOT change the default behavior of `owloop run` when `--no-tui` / `--plain` is absent.
- Do NOT remove or degrade the existing `OwloopTUI` path or its animation/summary behavior.
- Do NOT alter `EngineConfig` or `OwloopEngine` interfaces unless required solely to pass the new flag.

## Style
- Follow the existing `_common_run_options` decorator pattern in `src/owloop/cli.py` for adding boolean flags.
- Use `click.option("--no-tui/--tui", ...)` or `click.option("--no-tui", is_flag=True, ...)` consistent with adjacent `--worktree/--no-worktree` and `--subagents` options.
- Keep type hints consistent with the rest of `src/owloop/cli.py` (e.g., `bool = False`).
- Match existing ruff and pytest conventions in `tests/test_cli.py` (`CliRunner`, isolated filesystems, small focused assertions).

## Stuck Behavior
If you cannot make progress after 2 attempts at the same error, add a `## Blockers` section to this spec describing what's blocking you, commit your partial work, and output `<promise>DONE</promise>`.

## Verification
After each change, run:
- `uv run pytest tests/ -q`
- `uv run ruff check src/owloop tests`
- `uv run mypy src/owloop tests`

## Baseline
- `uv run owloop run --help` currently shows no `--no-tui` or `--plain` option.
- `src/owloop/cli.py:_run_engine` currently selects `OwloopTUI` based solely on `sys.stdout.isatty()`.
- `tests/test_cli.py` currently passes with 17 tests and has no coverage for `--no-tui` / `--plain`.

Output when complete:

<promise>DONE</promise>
