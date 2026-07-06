# Linter Zero-New-Violations Checklist

## Goal

Changed files must not introduce new linter warnings or errors. Existing violations in unchanged code are out of scope.

## Why zero-new instead of zero-total?

Most real projects have pre-existing lint debt. Requiring "0 errors" across the whole project will cause the loop to fix unrelated files, expanding scope and increasing risk. The correct target is **no new violations in changed lines**.

## Step 1: Detect configured linters

Check for config files in the project root and common locations.

### Python

| Config file / section | Linter |
|---|---|
| `pyproject.toml` → `[tool.ruff]` | Ruff |
| `pyproject.toml` → `[tool.mypy]`, `mypy.ini` | mypy |
| `pyproject.toml` → `[tool.pyright]`, `pyrightconfig.json` | Pyright |
| `.flake8`, `setup.cfg` → `[flake8]` | Flake8 |
| `.pylintrc` | Pylint |

### JavaScript / TypeScript

| Config file | Linter |
|---|---|
| `.eslintrc*`, `eslint.config.*` | ESLint |
| `biome.json`, `biome.jsonc` | Biome |
| `.prettierrc*`, `prettier.config.*` | Prettier |
| `deno.json`, `deno.jsonc` | Deno lint |

### Go, Rust, Ruby, etc.

| Config file | Linter |
|---|---|
| `.golangci.yml` | golangci-lint |
| `Cargo.toml` | `cargo clippy` |
| `.rubocop.yml` | RuboCop |

## Step 2: Identify changed files

```bash
git diff --name-only --diff-filter=ACMR HEAD
```

Use `--diff-filter=ACMR` to include Added, Copied, Modified, Renamed files (skip Deleted).

## Step 3: Run linters on changed files only

```bash
# Python example
FILES=$(git diff --name-only --diff-filter=ACMR HEAD | grep '\.py$' || true)
[ -n "$FILES" ] && uv run ruff check $FILES
[ -n "$FILES" ] && uv run mypy $FILES
```

## Step 4: Cross-reference with diff hunks

If the linter reports a violation, confirm the file/line is inside a changed hunk:

```bash
git diff -U0 HEAD -- <file> | grep '^@@' | sed 's/.*+\([0-9]*\),\?\([0-9]*\).*/\1 \2/'
```

This gives `start_line count` pairs for added/modified lines. Only fail the spec if the violation falls inside these ranges.

## Classification

| Condition | Severity | Action |
|---|---|---|
| New error in changed line | **P0** | Must fix before merge |
| New warning in changed line | **P2** | Should fix in this PR |
| Pre-existing violation in unchanged code | — | Out of scope |
| Formatter-only issue | **P3** | Suggest auto-fix command |

## Common Auto-fix Commands

| Linter | Auto-fix |
|---|---|
| Ruff | `ruff check --fix <files>` |
| ESLint | `npx eslint --fix <files>` |
| Biome | `npx biome check --write <files>` |
| Prettier | `npx prettier --write <files>` |
| RuboCop | `rubocop -A <files>` |
| cargo clippy | `cargo clippy --fix` |

## Spec-level Criterion Template

```bash
# Fail if any new Python lint error appears in changed files
FILES=$(git diff --name-only --diff-filter=ACMR HEAD | grep '\.py$' || true)
[ -z "$FILES" ] && exit 0
uv run ruff check $FILES
```

Expected: `0 errors`.

## Edge Cases

- **No linter detected**: Skip this gate and note it in the spec.
- **Generated files**: Skip paths like `node_modules/`, `dist/`, `build/`, `*_generated.*`.
- **Monorepo**: Run the linter with the config closest to the changed file.
