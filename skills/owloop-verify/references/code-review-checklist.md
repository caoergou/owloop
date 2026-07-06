# Automated Code Review Checklist for Owloop

This checklist separates what an unattended loop can verify from what requires a human reviewer.

## Machine-Checkable Gates

Add these to your spec's `## Verification` section when they apply.

### Scope discipline

- [ ] Only files listed in `## Requirements` were modified.
- [ ] No files listed in `## Exclusions` were modified.
- [ ] New files are in expected directories.

```bash
# List changed files and compare against spec scope
git diff --name-only
```

### Test integrity

- [ ] Existing tests were not deleted, commented out, or weakened.
- [ ] New tests cover the changed behavior.
- [ ] Test names describe behavior, not implementation.

```bash
# Check for weakened tests in diff
git diff -- tests/ | grep -E '^-\s+assert' && echo "WEAKENED TESTS DETECTED"
```

### Dependency discipline

- [ ] `pyproject.toml`, `package.json`, or equivalent config files are unchanged unless the spec explicitly requires it.
- [ ] No new runtime dependencies were added without explicit approval.
- [ ] `uv.lock`, `package-lock.json`, or equivalent lockfiles are consistent.

```bash
git diff --stat pyproject.toml uv.lock package.json
```

### Code hygiene

- [ ] No `TODO`, `FIXME`, `HACK`, or `XXX` left in changed code.
- [ ] No debug `print()`, `console.log()`, or `debugger` statements left.
- [ ] No unused imports or variables.
- [ ] No dead code.

```bash
git diff --diff-filter=AM -U0 | grep -E '^\+.*(TODO|FIXME|HACK|XXX)'
git diff --diff-filter=AM -U0 | grep -E '^\+.*(print\(|console\.log|debugger)'
```

### Complexity and duplication

- [ ] New functions are not excessively complex.
- [ ] No obvious duplication introduced.
- [ ] Existing complexity rules still pass.

```bash
# Python example
radon cc -nc src/
# or rely on ruff complexity rules
ruff check src/
```

### Security surface

- [ ] No secrets, passwords, or API keys in diff.
- [ ] No SQL injection / command injection patterns introduced.
- [ ] No unsafe eval or exec.

```bash
git diff | grep -Ei '(password|secret|api_key|token|eval\(|exec\()'
```

## Human-Review Triggers

If any of these apply, the spec should end with a request for human review rather than `<promise>DONE</promise>`.

- Changes affect authentication, authorization, or cryptography.
- Changes modify database schema or migrations.
- Changes alter public API contracts or response formats.
- Changes delete or significantly refactor existing modules.
- Changes introduce new runtime dependencies.
- Changes affect performance-sensitive paths without benchmarks.
- Changes touch configuration that affects production behavior.

When triggered, output:

```text
<promise>BLOCKED:needs-human-review — changes touch [area] and require human approval before merge</promise>
```

## Spec Template Snippet

```markdown
## Automated Review Gate

Run before claiming completion:

```bash
./scripts/check-scope.sh
./scripts/check-test-integrity.sh
./scripts/check-no-todo.sh
```

If any check fails, fix it or escalate to human review.
```
