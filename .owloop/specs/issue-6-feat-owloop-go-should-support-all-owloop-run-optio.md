# Feature: feat: owloop go should support all owloop run options

## Priority: 3

## Requirements
## Problem

`owloop go \"goal\"` is advertised in the README as the one-command entry point, but it currently hard-codes most runtime parameters in `src/owloop/cli.py`:

```python
_run_engine(
    0, True, model, "claude",
    3600, 0, 0,
    ascii=ascii, no_color=no_color, compact=compact,
)
```

This means users cannot pass `--max-tokens`, `--max-duration`, `--subagents`, `--verifier-model`, `--agent=kimi`, etc. when using the `go` flow. If they discover they need budget control or a different agent, they must abandon `go` and re-run `owloop spec` + `owloop run` separately.

## Expected behavior

`owloop go` should accept the same set of options as `owloop run` (via `_common_run_options`) so that a single command can express the full configuration, e.g.:

```bash
owloop go "refactor error handling" \
  --agent kimi \
  --max-tokens 100k \
  --max-duration 120 \
  --subagents
```

## Acceptance criteria


## Related

- `src/owloop/cli.py` `_common_run_options`, `_run_engine`, and the `go` command

## Acceptance Criteria
Candidate acceptance criteria derived from issue checklist items:

- [ ] `owloop go --help` shows the same runtime options as `owloop run --help`
- [ ] Options are forwarded correctly to `_run_engine` / `EngineConfig`
- [ ] Existing defaults (Claude, 3600s idle timeout, worktree enabled) remain unchanged when options are omitted
- [ ] Add/update tests in `tests/test_cli.py`

## Exclusions
[What NOT to do — be explicit. This is what keeps an autonomous run from wandering.]

- Do not modify [file/module]
- Do not change [behavior]

## Style
[Coding conventions to follow so generated code matches the existing codebase]

- Follow the existing pattern in [file/module]
- [Naming/formatting/library conventions]

## Stuck Behavior
[What to do if the agent cannot make progress]

If you cannot make progress after 2 attempts at the same error, add a `## Blockers`
section to this spec describing what's blocking you, commit your partial work, and
output `<promise>DONE</promise>`.

## Verification
[Exact commands to run after each change, before claiming completion]

```bash
[test command]
[lint command]
```

## Baseline
[Calibration data recorded before the loop started — helps track progress]

- [command]: [current value] → target [target value]

Output when complete: `<promise>DONE</promise>`
