# Spec: agents-md-self-learning

Status: COMPLETE

## Priority: 5

## Depends On
- none

## Requirements
- [x] Add an `OperationalLearnings` tracker that captures operational discoveries during a run (e.g., "tests require a running database", "use poetry not pip").
- [x] Write learnings to `.owloop/learnings.md` in a simple append-only format with timestamps.
- [x] Load `.owloop/learnings.md` into the build prompt context on subsequent iterations, similar to `run-notes.md`.
- [x] On fix-loop detection (same files modified 3+ rounds), automatically split the current spec into smaller pieces or emit `<promise>BLOCKED:...>` with a concrete reason.
- [x] Add the learning-recording instructions to the default build prompt template.

## Acceptance Criteria
- [x] `uv run pytest tests/test_learnings.py -q` → all passed.
- [x] After a run writes `.owloop/learnings.md`, the next build prompt includes those learnings.
- [x] A spec that triggers the fix-loop threshold is split into sub-specs or marked blocked.
- [x] Existing death-spiral warning still fires when auto-recovery is not possible.

## Exclusions
- Do NOT modify the top-level `AGENTS.md` file directly unless the learning explicitly applies project-wide.
- Do NOT remove the existing fix-loop warning.
- Do NOT change the build prompt structure beyond appending a learnings section.

## Style
- Follow the existing prompt-template pattern in `templates/PROMPT_build.md`.
- Keep learning entries short and actionable.

## Stuck Behavior
If a learning cannot be safely appended (file locked), log it and continue.

## Verification
```bash
uv run pytest tests/test_learnings.py -q
uv run pytest tests/test_engine.py -q
```

## Baseline
- Operational knowledge discovered in one iteration is lost for the next.
- Fix loops are only warned, not recovered from.

Output when complete: `<promise>DONE</promise>`
