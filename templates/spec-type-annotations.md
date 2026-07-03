# Spec: Add type annotations to [module]

## Priority: [1-5]

## Requirements

Add type annotations to [target module/package] so it passes `mypy --strict` without errors.

## Acceptance Criteria

- [ ] `mypy --strict [module]` → 0 errors
- [ ] Existing tests pass: `[command]`
- [ ] No runtime behavior changed: `[command]`
- [ ] Public API signatures remain compatible: `[command]`

## Exclusions

- Do NOT refactor logic while adding types.
- Do NOT change function signatures in a breaking way.
- Do NOT modify files outside the target module.
- Do NOT suppress errors with `# type: ignore` unless explicitly approved.

## Style

- Use the project's existing type annotation style.
- Prefer `from __future__ import annotations` when the codebase already uses it.
- Use `typing` names consistent with the project's Python version support.

## Verification

```bash
mypy --strict [module]
pytest [relevant tests]
ruff check [path]
```

## Baseline

- `mypy --strict [module]`: [current error count] → target 0

Output when complete: `<promise>DONE</promise>`
