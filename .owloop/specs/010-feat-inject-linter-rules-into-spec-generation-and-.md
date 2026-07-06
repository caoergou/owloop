# Feature: feat: inject linter rules into spec generation and auto-retry on lint errors

**Status**: COMPLETE

## Priority: 3

## Requirements

- Export a machine-readable summary of `SpecLinter` rules so the generator can reference them without duplicating logic.
- Inject the linter rule summary into `SPEC_GENERATION_PROMPT` so Step 8 (self-check) explicitly requires generated specs to satisfy `SpecLinter` validation.
- After the agent returns generated specs, run `SpecLinter.lint_spec()` on each candidate spec before writing it to disk.
- If lint errors exist, feed the lint findings back to the agent and retry generation up to a configurable limit (default 1 retry).
- Add unit tests in `tests/test_spec_generator.py` covering: rule export, prompt injection, lint-before-write, and the retry path on lint errors.

## Acceptance Criteria

- [ ] `uv run pytest tests/test_spec_generator.py -q` → all passed.
- [ ] `uv run python -c "from owloop.spec_linter import SpecLinter; print(SpecLinter('src/owloop').rules_summary())"` → prints a non-empty string containing "backtick" and "exclusions".
- [ ] `uv run python -c "import owloop.spec_generator as sg; assert 'linter' in sg.SPEC_GENERATION_PROMPT.lower() and 'backtick' in sg.SPEC_GENERATION_PROMPT.lower()"` → exits 0.
- [ ] `uv run python -c "from owloop.spec_generator import SpecGenerator; assert 'lint' in SpecGenerator.__init__.__doc__.lower() if SpecGenerator.__init__.__doc__ else True"` → exits 0.
- [ ] `uv run pytest tests/test_spec_generator.py::test_lint_retry_on_invalid_spec -q` → all passed.
- [ ] `uv run pytest tests/ -q` → all passed.

## Exclusions

- Do NOT modify `pyproject.toml` or `uv.lock`.
- Do NOT change unrelated tests in `tests/` outside of `tests/test_spec_generator.py`.
- Do NOT break existing CLI commands (`owloop spec`, `owloop check`, `owloop go`).
- Do NOT modify `owloop/backpressure.py`, `owloop/paths.py`, or `owloop/spec_queue.py`.

## Style

- Follow existing type-hint conventions (`from __future__ import annotations`, `Path | None`, explicit return types).
- Match the ruff configuration in `pyproject.toml` (line-length 100, Google docstrings).
- Use `pytest` fixtures and `tmp_path` as shown in `tests/test_spec_generator.py`.
- Keep new public methods small and focused; reuse `SpecLinter.lint_spec()` rather than inlining lint logic.

## Stuck Behavior

If you cannot make progress after 2 attempts at the same error, add a `## Blockers` section to this spec describing what's blocking you, commit your partial work, and output `<promise>DONE</promise>`.

## Verification

- `uv run pytest tests/ -q`
- `uv run ruff check src/owloop tests`
- `uv run mypy src/owloop tests`

## Baseline

- `SpecGenerator` and `SpecLinter` currently operate independently; no automatic lint feedback loop exists.
- `uv run pytest tests/ -q` currently passes on the existing test suite.
- `uv run owloop check` currently reports warnings/errors on generated specs only after manual generation.

<promise>DONE</promise>
