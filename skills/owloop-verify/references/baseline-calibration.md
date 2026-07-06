# Baseline Calibration

Before the loop starts, run every proposed verification command in the **current** codebase and record the result. This baseline prevents two common loop failures:

1. **Already-passing criteria** — the loop exits on iteration 1 with no work done.
2. **Impossible targets** — the loop can never pass because the baseline is too far from the target.

## Calibration Workflow

### Step 1: Run the command as written

Use the exact command you plan to put in the spec's `## Verification` section.

```bash
$ uv run pytest tests/test_auth.py -q
no tests ran
```

```bash
$ uv run ruff check src/ 2>&1 | tail -1
Found 84 errors.
```

### Step 2: Classify the result

| Result | Meaning | Action |
|---|---|---|
| Passes already | Target is already met | Make stricter, or pick a different task |
| Fails with a small, scoped gap | Good candidate for loop | Set target slightly better than baseline |
| Fails because of unrelated debt | Spec will be blamed for pre-existing failures | Exclude unrelated files in `## Exclusions` |
| Crashes or missing infra | Loop can never pass | Fix infra first, or choose a different criterion |

### Step 3: Record in the spec

Add a `## Baseline` section to the spec:

```markdown
## Baseline

| Criterion | Current | Target | Notes |
|---|---|---|---|
| `uv run ruff check src/owloop` | 12 errors | ≤ 12 errors | No new errors allowed |
| `uv run pytest tests/test_auth.py -q` | 0 passed | 1 passed | Add test for new behavior |
```

### Step 4: Write the criterion as a shell command

Target must be concrete:

- **Good**: `uv run pytest tests/test_auth.py -q | grep -q "1 passed"`
- **Bad**:  `uv run pytest tests/test_auth.py -q` (output may change timing)

For count-based targets, prefer thresholds over exact counts when the exact number fluctuates:

```bash
uv run ruff check src/owloop 2>&1 | grep -oP '\d+(?= errors?)' | awk '{print ($1 <= 12 ? "OK" : "FAIL")}'
```
Expected output: `OK`.

## Examples

### Example 1: New feature with no existing tests

```bash
$ uv run pytest tests/test_billing.py -q
no tests ran

# Baseline: 0 tests
# Target: 1 passed
```

### Example 2: Refactor with existing lint debt

```bash
$ uv run ruff check src/ 2>&1 | tail -1
Found 84 errors.

# Baseline: 84 errors
# Realistic target for this spec: ≤ 40 errors
# Follow-up spec: ≤ 5 errors
```

### Example 3: Pre-existing failures outside scope

```bash
$ uv run pytest tests/ -q
FAILED tests/test_legacy.py::test_old_feature
1 failed, 120 passed

# The failure is in test_legacy.py, unrelated to this spec.
# Exclude it: run `uv run pytest tests/ --ignore=tests/test_legacy.py -q`
```

## Checklist

- [ ] I ran every verification command before writing the spec.
- [ ] I recorded the current output in `## Baseline`.
- [ ] I set a target that is achievable within this spec's scope.
- [ ] I listed unrelated failures in `## Exclusions`.
