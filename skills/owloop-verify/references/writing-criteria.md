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
