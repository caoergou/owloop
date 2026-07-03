# Spec: Clean up ML/DS code — [target]

## Priority: [1-5]

## Requirements

Clean up [target notebook/module] by [specific task, e.g., converting a notebook to a script, adding type annotations, standardizing logging, removing dead experiment code].

## Acceptance Criteria

- [ ] Converted script compiles: `python -m py_compile [script].py`
- [ ] Existing tests pass: `[command]`
- [ ] No broken imports: `[command, e.g., python -c "import [module]"]`
- [ ] Linter passes: `[command]`

## Exclusions

- Do NOT modify model weights or model files.
- Do NOT change training hyperparameters.
- Do NOT alter evaluation metrics logic.
- Do NOT change model inference code without an explicit eval step.
- Do NOT check large artifacts into git.

## Style

- Follow existing project conventions.
- Keep experiment reproducibility intact (seeds, configs, dependency pins).

## Verification

```bash
python -m py_compile [script].py
pytest [relevant tests]
mypy [module]
ruff check [path]
```

## Baseline

- [command]: [current value] → target [target value]

Output when complete: `<promise>DONE</promise>`
