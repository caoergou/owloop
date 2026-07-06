# Writing Acceptance Criteria

Every acceptance criterion must be a **runnable shell command with a concrete expected output**.

## Exact matching

```bash
# Exact
$ uv run pytest tests/test_auth.py -q
1 passed in 0.03s

# Fuzzy (when exact is fragile)
$ uv run pytest tests/test_auth.py -q | grep -c passed
1
```

## Count-based criteria

```bash
# Good: bounded count
$ grep -c "print(" src/ | awk '{s+=$1} END {print s}'
0

# Good: threshold
$ uv run ruff check src/ 2>&1 | grep -oP '\d+(?= errors?)' || echo 0
3
```

## File existence / content criteria

```bash
# File exists
$ test -f src/owloop/adapters.py && echo yes
yes

# Content present
$ grep -q "class KimiCodeAdapter" src/owloop/adapters.py && echo yes
yes

# Content absent
$ grep -q "class OldAdapter" src/owloop/adapters.py && echo "FAIL" || echo "OK"
OK
```

## Criteria by Stack

### Python

```bash
uv run pytest tests/test_x.py -q
uv run ruff check src/ tests/
uv run mypy src/
```

### Node / TypeScript

```bash
npm run lint
npm run typecheck
npm test -- --run tests/test_x.test.ts
```

### Go

```bash
go test ./pkg/x/...
go vet ./pkg/x/...
```

### Rust

```bash
cargo test -p crate_name
cargo clippy -- -D warnings
```

## Classifying Criteria: P0 / P1 / P2 / P3

| Level | When to use | Example |
|---|---|---|
| **P0** | Safety, correctness, security | New tests pass, no secrets in diff |
| **P1** | Functional completion required | Spec-specific command returns expected output |
| **P2** | Quality strongly preferred | Complexity threshold, coverage not dropped |
| **P3** | Advisory | Style suggestion, optional refactor |

Mark the level in the spec so the loop knows which failures are blockers:

```markdown
## Acceptance Criteria

- [P0] `uv run pytest tests/test_x.py -q` → `1 passed`
- [P1] `git diff --name-only` → only `src/owloop/x.py` and `tests/test_x.py`
- [P2] `uv run radon cc -nc src/owloop/x.py` → no block above complexity 10
```

## Common pitfalls

1. **Criteria that depend on AI judgment**
   - Bad: "The refactor improves readability."
   - Good: "`uv run ruff check src/` returns 0 errors."

2. **Criteria that are already true**
   - Bad: Criterion passes before any work is done.
   - Fix: Make it stricter or choose a different task.

3. **Criteria that are never true**
   - Bad: Target is impossible given the baseline.
   - Fix: Adjust target or split the work.

4. **Flaky criteria**
   - Bad: Test that passes 80% of the time.
   - Fix: Exclude flaky tests or make them deterministic.

5. **Criteria outside the agent's control**
   - Bad: "Deploy to production."
   - Good: "CI pipeline passes on the branch."

6. **Trusting the agent to self-grade**
   - Bad: Loop iteration reports "looks good" without running commands.
   - Good: Every claim is backed by a shell command in the log.

7. **Grepping full project instead of diff**
   - Bad: `ruff check src/` in a project with 100 pre-existing errors.
   - Good: Run `ruff check` only on changed files, or set a "no new errors" threshold.

## Writing a Deterministic Criterion

1. Start with the command the agent will run.
2. Decide whether exact output or a condition is more stable.
3. If using a condition, make the pass/fail explicit with `&& echo OK || echo FAIL`.
4. Run it before the loop to establish a baseline.
5. Record expected output in the spec.

## Example: Multi-layer Criterion

```markdown
## Acceptance Criteria

- [P0] `uv run pytest tests/test_billing.py -q | grep -c "passed"` → `2`
- [P1] `git diff --name-only` → contains `src/owloop/billing.py` and `tests/test_billing.py`
- [P1] `git diff -- tests/test_billing.py | grep -E '^-(\s*)(assert|expect)'` → empty
- [P2] `uv run ruff check src/owloop/billing.py tests/test_billing.py` → 0 errors
- [P2] `uv run mypy src/owloop/billing.py` → 0 errors
```
