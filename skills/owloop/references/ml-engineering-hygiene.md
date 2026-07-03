# ML / Data Science Engineering Hygiene Reference

Target: read this when a spec touches ML/DS code.

## What owloop Is NOT For

Do not use the autonomous loop for:

- Model training or tuning.
- Hyperparameter search.
- Neural architecture search.

For these, recommend a dedicated tool such as Optuna, FLAML, Ray Tune, or goal-md.

## What owloop IS For

These are mechanical, verifiable tasks:

- Notebook-to-script conversion.
- Data pipeline refactoring.
- Adding type annotations.
- Generating tests for utility functions.
- Updating dependencies and imports.
- Import cleanup and organization.
- Logging standardization.
- Removing dead experiment code.

## Verification Examples

After each change, run the appropriate checks:

```bash
python -m py_compile <script>.py
pytest <relevant tests>
mypy <module>
ruff check <path>
```

## Safety Rules

- Do not change model inference logic without an evaluation pass.
- Do not alter data schemas without pipeline tests.
- Keep experiment reproducibility: do not delete seeds, configs, or dependency pins without explicit approval.
- Never check model weights or large artifacts into git.

## Spec Templates

See `templates/spec-ml-hygiene.md` for a ready-to-use spec template.
