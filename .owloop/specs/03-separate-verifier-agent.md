# Spec: separate-verifier-agent

Status: COMPLETE

## Priority: 2

## Depends On
- `02-auto-discover-backpressure-commands.md`

## Requirements
- [x] After an executor agent emits `<promise>DONE</promise>`, spawn a separate verifier agent with a fresh context that checks the work independently.
- [x] The verifier agent reads the current spec's requirements and acceptance criteria, runs each verification command, and reports `PASS` or `FAIL` with concrete evidence.
- [x] The iteration is only counted as complete when the verifier returns `PASS`.
- [x] On `FAIL`, the verifier output is appended to the next iteration's context so the executor can retry.
- [x] Add `--verifier-model` option to `owloop run` defaulting to the executor model.

## Acceptance Criteria
- [x] `uv run pytest tests/test_verifier.py -q` → all passed.
- [x] A mock executor that emits `<promise>DONE</promise>` without doing work is rejected by the verifier.
- [x] A mock executor that completes the spec's acceptance criteria is accepted by the verifier.
- [x] `OwloopEngine.run()` returns a summary whose `verified` field reflects verifier results.

## Exclusions
- Do NOT remove the existing `<promise>DONE</promise>` parsing.
- Do NOT modify the executor agent adapter interface beyond adding a way to spawn a verifier.
- Do NOT change the CLI commands other than `owloop run` options.

## Style
- Mirror the existing adapter pattern in `src/owloop/adapters.py`.
- Keep verifier prompts focused and small; reuse `SpecLinter` and backpressure discovery where possible.

## Stuck Behavior
If the verifier fails more than twice on the same spec, mark the iteration as blocked and stop the loop with reason `verification_failed`.

## Verification
```bash
uv run pytest tests/test_verifier.py -q
uv run pytest tests/test_engine.py -q
```

## Baseline
- Completion is determined solely by `<promise>DONE</promise>`.
- No independent verification exists today.

Output when complete: `<promise>DONE</promise>`
