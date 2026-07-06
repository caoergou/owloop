# Spec: auto-discover-backpressure-commands

Status: COMPLETE

## Priority: 1

## Depends On
- none

## Requirements
- [x] Add a backpressure discovery module that scans the project for common verification command sources (`pyproject.toml`, `package.json`, `Makefile`, `Cargo.toml`, `.github/workflows/*.yml`).
- [x] Extract runnable verification commands for each discovered source (tests, lint, type check, build).
- [x] Persist discovered commands in `.owloop/backpressure.json` with a stable schema: `{ "commands": [{"name": "...", "command": "...", "source": "..."}] }`.
- [x] Expose the discovery through a new CLI command `owloop discover` and call it automatically during `owloop init` if no `.owloop/backpressure.json` exists.
- [x] Make the spec generator and linter read `.owloop/backpressure.json` so generated specs default to project-appropriate verification commands.

## Acceptance Criteria
- [x] `uv run owloop discover` in this repo produces `.owloop/backpressure.json` containing at least `pytest tests/`, `ruff check src/`, and `mypy src/`.
- [x] `uv run pytest tests/test_backpressure.py -q` → all passed.
- [x] `uv run owloop init` in a fresh git repo creates `.owloop/backpressure.json` when it does not already exist.
- [x] Invalid/missing config files are skipped without error; an empty result is written as `{ "commands": [] }`.

## Exclusions
- Do NOT modify `pyproject.toml`, `uv.lock`, or existing test logic in unrelated files.
- Do NOT require network access or external API calls for discovery.
- Do NOT change the existing `owloop run` loop behavior beyond reading `.owloop/backpressure.json` when present.

## Style
- Follow the existing patterns in `src/owloop/spec_linter.py` and `src/owloop/spec_generator.py`.
- Use `pathlib.Path` for filesystem operations.
- Keep parsing simple: `tomllib` for TOML, `json` for JSON, plain regex/line scanning for Makefile and YAML.

## Stuck Behavior
If a config file format cannot be parsed cleanly, skip it and log a warning rather than fail.

## Verification
```bash
uv run pytest tests/test_backpressure.py -q
uv run owloop discover
```

## Baseline
- `.owloop/backpressure.json` does not exist.
- Generated specs currently rely on manually written acceptance criteria commands.

Output when complete: `<promise>DONE</promise>`
