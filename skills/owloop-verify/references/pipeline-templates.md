# Verification Pipeline Templates

Use these as starting points. Copy the relevant blocks into the spec's `## Verification` section and adjust paths/tools to the project.

> **Note:** These are copy-paste command templates, not project-managed executable scripts. Project stacks differ too much for one script to be universally correct.

## Python (uv / ruff / pytest)

```bash
# 1. Static checks
uv run ruff check src/ tests/
uv run mypy src/

# 2. Scope discipline
git diff --name-only

# 3. Test integrity
git diff -- tests/ | grep -E '^-(\s*)(assert|expect)' && echo "WARNING: assertions removed"

# 4. Change-trap scan
git diff --diff-filter=AM -U0 | grep -E '^\+.*(TODO|FIXME|print\(|debugger;|import pdb)'

# 5. Tests
uv run pytest tests/ -q
```

## Node / TypeScript (npm / eslint / vitest)

```bash
# 1. Static checks
npm run lint
npm run typecheck

# 2. Scope discipline
git diff --name-only

# 3. Test integrity
git diff -- tests/ | grep -E '^-(\s*)(expect|assert|it\(|test\()' && echo "WARNING: tests changed"

# 4. Change-trap scan
git diff --diff-filter=AM -U0 | grep -E '^\+.*(console\.log|debugger;|TODO|FIXME)'

# 5. Tests
npm test -- --run
```

## Go

```bash
go vet ./...
go test ./...
git diff --name-only
git diff --diff-filter=AM -U0 | grep -E '^\+.*(TODO|FIXME|fmt\.Print)'
```

## Rust

```bash
cargo check
cargo clippy -- -D warnings
cargo test
git diff --name-only
git diff --diff-filter=AM -U0 | grep -E '^\+.*(TODO|FIXME|println!)'
```

## How to adapt

1. Replace `src/` and `tests/` with your project's actual directories.
2. Replace tool names if you use different linters or test runners.
3. Remove any step that does not apply to the current spec's scope.
4. For each remaining step, write the expected output in the spec's `## Verification` section.
