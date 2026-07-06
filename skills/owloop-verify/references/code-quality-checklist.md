# Code Quality Checklist

Machine-checkable quality gates for error handling, performance, and boundary conditions. Judgment-based quality concerns should be deferred to human review.

## Error Handling

### Anti-patterns to flag

| Pattern | Check |
|---|---|
| Swallowed exceptions | `grep -R "except.*:.*$\|except.*pass" src/owloop/` |
| Overly broad catch | `grep -R "except Exception\|except BaseException" src/owloop/ \| wc -l` |
| Missing error handling | static analysis only; pair with test coverage |

### Spec-level criterion

```bash
# No bare except/pass in changed Python files
FILES=$(git diff --name-only --diff-filter=ACMR HEAD | grep '\.py$' || true)
[ -z "$FILES" ] && exit 0
grep -E "except\s*\w*\s*:\s*$|except\s*\w*\s*:\s*pass" $FILES && echo "FAIL" || echo "OK"
```

Expected: `OK`.

## Performance

| Concern | Check |
|---|---|
| N+1 query pattern | grep for loops containing query-like calls |
| Missing timeouts | grep for network calls without `timeout=` |
| Unbounded collections | grep for `while True` or unbounded list growth |

### Spec-level criterion

```bash
# New network calls must include timeout
FILES=$(git diff --name-only --diff-filter=ACMR HEAD | grep '\.py$' || true)
[ -z "$FILES" ] && exit 0
grep -E "requests\.get\(|httpx\.get\(" $FILES | grep -v "timeout" && echo "FAIL" || echo "OK"
```

Expected: `OK`.

## Boundary Conditions

| Concern | Check |
|---|---|
| Division without zero guard | `grep -E "/ [a-zA-Z_]+"` in diff and review |
| Array access without length check | `grep -E "\[0\]"` in diff and review |
| Truthy check excluding valid falsy values | review manually |

### Spec-level criterion

Most boundary checks require targeted unit tests rather than grep. Add a test file and gate it:

```bash
uv run pytest tests/test_boundary_conditions.py -q
```

Expected: all passed.

## Test Coverage

| Concern | Check |
|---|---|
| Coverage dropped | `coverage report --fail-under=60` or project threshold |
| New code untested | `git diff --name-only` includes new code without matching test file |

### Spec-level criterion

```bash
uv run pytest --cov=src/owloop --cov-report=term-missing tests/test_module.py -q
```

Expected: no missing lines in the changed module (or within project threshold).

## Checklist Summary

- [ ] No swallowed or overly broad exceptions in changed files.
- [ ] No network calls without timeouts.
- [ ] No unbounded loops or recursion without safeguards.
- [ ] Boundary cases covered by tests.
- [ ] Coverage did not drop for the changed module.
