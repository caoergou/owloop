# Spec: Refactor [X] while preserving behavior

## Priority: [1-5]

## Requirements

Refactor [target file/behavior] to [goal, e.g., reduce complexity, remove duplication, improve naming] while preserving existing behavior.

## Acceptance Criteria

- [ ] Characterization tests pass before the refactor: `[command]`
- [ ] Existing tests pass after the refactor: `[command]`
- [ ] Linter passes: `[command]`
- [ ] No public interface changed: `[command to verify signatures/callers]`

## Exclusions

- Do NOT change public interfaces or API contracts.
- Do NOT modify business logic.
- Do NOT touch auth, crypto, or payments code.
- Do NOT change SQL queries or data schemas.
- Do NOT modify files outside the listed blast radius.

## Style

- Follow existing project conventions.
- Prefer small, reversible commits.

## Verification

```bash
[test command]
[lint command]
[diff-review command]
```

## Baseline

- [command]: [current value] → target [target value]

Output when complete: `<promise>DONE</promise>`
