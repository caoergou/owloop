---
name: owloop-verify
description: >-
  Verification pipeline design for Owloop — how to write shell-verifiable
  acceptance criteria, calibrate baselines, and build a verification chain
  that an autonomous loop can evaluate deterministically.
  Use when a spec's acceptance criteria are vague, the loop can't tell if
  it's done, or you need to design a verification pipeline.
license: MIT
compatibility: Requires owloop methodology; works with any agentskills.io-compatible agent
metadata:
  author: caoergou
  version: "0.3.0"
  repository: https://github.com/caoergou/owloop
---

# Owloop Verification

Verification is the keystone of loop engineering. If "done" cannot be checked by a shell command, the loop cannot terminate reliably. This skill teaches how to design verifiable acceptance criteria and calibrate baselines.

## When to Use

Use this skill when:
- A spec's acceptance criteria are vague or subjective
- The loop exits without doing real work (already-passing criteria)
- The loop can never pass (broken infrastructure or impossible targets)
- You need to design a verification pipeline for a new project

## The Golden Rule

Every acceptance criterion must be a **runnable shell command with a concrete expected output**.

- Good: `uv run pytest tests/test_auth.py -q` → `1 passed`
- Good: `grep -c "except ValidationError" backend/app/api/*.py` → `≤ 5`
- Bad: "Error handling is properly unified"
- Bad: "The code works correctly"

## Baseline Calibration

Run the proposed verification command BEFORE the loop starts. Record the current state and set a realistic target.

### Why calibrate?

| Baseline finding | What it means | Action |
|---|---|---|
| Command already passes | Spec will exit on iteration 1 with no work done | Make the criterion stricter or pick a different task |
| Command crashes | Loop can never pass | Fix infrastructure first, or exclude the broken part |
| Baseline is far from target | Target is unrealistic | Split into smaller specs or adjust target |
| Pre-existing failures unrelated to scope | Spec is doomed | Exclude them explicitly |

### Example calibration

```bash
# Proposed criterion: "ruff errors ≤ 5"
$ uv run ruff check backend/ 2>&1 | tail -1
Found 84 errors.

# Baseline: 84 errors
# Realistic target: ≤ 40 in this spec, then another spec for ≤ 5
```

## Verification Pipeline Design

A strong verification pipeline has multiple layers, ordered from fast/cheap to slow/expensive:

```
1. Static checks (fast)         → ruff, mypy, eslint, prettier
2. Automated code review (fast) → scope, test integrity, dependency checks
3. Unit tests (medium)          → pytest, jest, vitest
4. Integration tests (slow)     → API tests, database tests
5. End-to-end checks            → smoke tests, build verification
```

For an autonomous loop, prefer:
- **Fast feedback**: commands that return in seconds, not minutes
- **Deterministic output**: same input → same output every time
- **No network**: avoid tests that depend on external services
- **Clear pass/fail**: exit code 0 or 1, not a report to interpret

## Automated Code Review Gate

Code review and verification overlap: both ask "is this change good enough to merge?" The difference is that verification checks functional correctness, while code review checks engineering quality. In an unattended loop, **only the machine-checkable parts of code review can become gates**.

### What CAN be automated

Add these checks to your verification pipeline when relevant:

| Review concern | Automated check | Example command |
|---|---|---|
| **Scope discipline** | Changed files match spec | `git diff --name-only` vs `## Requirements` / `## Exclusions` |
| **Test integrity** | Existing tests not weakened | `git diff -- tests/` shows no deleted assertions |
| **No surprise dependencies** | Lock/config files unchanged unless intended | `git diff --stat pyproject.toml uv.lock package.json` |
| **No leftover TODO/FIXME** | No unresolved markers in changed code | `git diff --diff-filter=AM -U0 | grep -E '^\+.*(TODO\|FIXME)'` |
| **No debug prints** | No `print()`/`console.log()` left behind | `git diff --diff-filter=AM -U0 | grep -E '^\+.*(print\(|console\.log)'` |
| **Complexity guard** | Cyclomatic complexity bounded | `radon cc -nc src/` or ruff complexity rules |
| **Dead code guard** | No unused imports/variables | `ruff check src/` |
| **Security surface** | No secrets in diff | `git diff | grep -Ei '(password\|secret\|api_key\|token)'` |

### What CANNOT be automated

Do NOT try to express these as acceptance criteria. They require human judgment and should be handled by:
- Marking the spec `Status: REVIEW_REQUIRED` instead of `COMPLETE`
- Adding a `## Security Review` or `## Design Review` section
- Outputting `<promise>BLOCKED:needs-human-review` instead of `<promise>DONE</promise>`

| Human-judgment concern | Why it can't be automated |
|---|---|
| Architecture fit | Requires understanding trade-offs |
| Naming clarity | Subjective; no shell command can judge |
| Over-engineering | Requires product context |
| Security-critical changes | Risk too high for unsupervised agent |
| UX/design decisions | Needs human taste and context |

### Recommended code-review gate in a spec

```markdown
## Verification

Run these commands before claiming completion:

```bash
# 1. Static checks
uv run ruff check src/ tests/
uv run mypy src/

# 2. Automated code-review gate
uv run pytest tests/ -q
./scripts/check-scope.sh        # verify only expected files changed
./scripts/check-no-todo.sh      # verify no TODO/FIXME in diff

# 3. Human review trigger (if applicable)
# If this spec touches auth/security/DB schema, stop here and ask for review.
```

Expected:
- `ruff`: 0 errors
- `mypy`: 0 errors
- `pytest`: all passed
- `check-scope.sh`: exit 0
- `check-no-todo.sh`: exit 0
```

## Writing Acceptance Criteria

### Use exact matching when possible

```bash
# Exact
$ uv run pytest tests/test_auth.py -q
1 passed in 0.03s

# Fuzzy (when exact is fragile)
$ uv run pytest tests/test_auth.py -q | grep -c passed
1
```

### Count-based criteria

```bash
# Good: bounded count
$ grep -c "print(" src/ | awk '{s+=$1} END {print s}'
0

# Good: threshold
$ uv run ruff check src/ 2>&1 | grep -oP '\d+(?= errors?)' || echo 0
3
```

### File existence / content criteria

```bash
# File exists
$ test -f src/owloop/adapters.py && echo yes
yes

# Content present
$ grep -q "class KimiCodeAdapter" src/owloop/adapters.py && echo yes
yes
```

## Common Pitfalls

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

## Verification Checklist for Specs

Before finalizing a spec, ask:

- [ ] Can I run every criterion from the project root with one command?
- [ ] Does each criterion have a concrete expected output?
- [ ] Did I run the criterion before writing the spec to establish a baseline?
- [ ] Are pre-existing failures listed in `## Exclusions`?
- [ ] Is the fastest/cheapest check listed first?
- [ ] Do the criteria cover both "the change was made" and "nothing else broke"?

## Example Verification Section

```markdown
## Verification

Run these commands after each change and before claiming completion:

```bash
# 1. Static checks
uv run ruff check src/owloop tests/

# 2. Type checks
uv run mypy src/owloop

# 3. Automated code-review gate
./scripts/check-scope.sh
./scripts/check-no-todo.sh

# 4. Unit tests
uv run pytest tests/test_adapters.py -q

# 5. Integration check
uv run owloop run --help | grep -q "kimi"
```

Expected results:
- `ruff`: 0 errors
- `mypy`: 0 errors
- `check-scope.sh`: exit 0
- `check-no-todo.sh`: exit 0
- `pytest`: all passed
- `owloop run --help`: contains `--agent [claude|kimi]`
```

## References

- [Automated Code Review Checklist](references/code-review-checklist.md)
