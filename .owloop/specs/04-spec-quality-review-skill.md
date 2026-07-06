# Spec: spec-quality-review-skill

Status: COMPLETE

## Priority: 3

## Depends On
- `02-auto-discover-backpressure-commands.md`

## Requirements
- [x] Add a `SpecReview` step that runs after spec generation and before execution.
- [x] Static checks: reuse `SpecLinter` to catch structural issues.
- [x] Executable checks: run each acceptance criteria command in dry-run/baseline mode to confirm it exists and is runnable.
- [x] Agent review: spawn a dedicated review agent that flags unrealistic targets, vague exclusions, scope creep, and missing edge cases.
- [x] Surface review results in `owloop check` and in the `spec` command output.
- [x] Auto-fix trivial issues (e.g., missing verification prefix) when safe; flag non-fixable issues for user approval.

## Acceptance Criteria
- [x] `uv run pytest tests/test_spec_review.py -q` → all passed.
- [x] `owloop check --review` runs static + executable + agent review and reports findings.
- [x] A spec with a non-existent command in acceptance criteria is flagged by executable checks.
- [x] A spec with vague exclusions (e.g., "don't break things") is flagged by agent review.

## Exclusions
- Do NOT change the default `owloop check` behavior without an explicit `--review` flag.
- Do NOT require the review agent to actually implement anything.
- Do NOT modify `spec_linter.py` beyond exposing a public API the review step can call.

## Style
- Follow the existing `SpecLinter`/`LintReport` patterns.
- Keep the review agent prompt in a template-like constant for easy tuning.

## Stuck Behavior
If the review agent is unavailable (no API key), fall back to static + executable checks only.

## Verification
```bash
uv run pytest tests/test_spec_review.py -q
uv run owloop check --review
```

## Baseline
- `owloop check` only runs structural linting.
- Spec quality is judged by the user before the loop starts.

Output when complete: `<promise>DONE</promise>`
