---
name: owloop-verify
description: >-
  Verification pipeline design for Owloop — how to write shell-verifiable
  acceptance criteria, calibrate baselines, detect common change traps,
  and build a verification chain that an autonomous loop can evaluate
  deterministically.
  Use when a spec's acceptance criteria are vague, the loop can't tell if
  it's done, you need to design a verification pipeline, or you want to
  guard against typical unattended-loop drift.
license: MIT
compatibility: Requires owloop methodology; works with any agentskills.io-compatible agent
metadata:
  author: caoergou
  version: "0.4.0"
  repository: https://github.com/caoergou/owloop
---

# Owloop Verification

Verification is the keystone of loop engineering. If "done" cannot be checked by a shell command, the loop cannot terminate reliably. This skill teaches how to design verifiable acceptance criteria, calibrate baselines, and guard against the drift that unattended loops naturally produce.

## When to Use

Use this skill when:
- A spec's acceptance criteria are vague or subjective
- The loop exits without doing real work (already-passing criteria)
- The loop can never pass (broken infrastructure or impossible targets)
- You need to design a verification pipeline for a new project
- You want to add automated change-trap checks to a spec

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

Add these checks to your verification pipeline when relevant. Treat them as **copy-paste command templates**, not as project-managed executable scripts. Adapt the path and tool names to the project stack.

| Review concern | What to check | Example command |
|---|---|---|
| **Scope discipline** | Changed files match spec scope | `git diff --name-only` then compare with `## Requirements` / `## Exclusions` |
| **Test integrity** | Existing tests not weakened | `git diff -- tests/` should not show deleted assertions or commented tests |
| **No surprise dependencies** | Lock/config files unchanged unless intended | `git diff --stat pyproject.toml uv.lock package.json package-lock.json` |
| **No leftover TODO/FIXME** | No unresolved markers in changed code | `git diff --diff-filter=AM -U0 \| grep -E '^\+.*(TODO\|FIXME)'` |
| **No debug prints** | No `print()`/`console.log()` left behind | `git diff --diff-filter=AM -U0 \| grep -E '^\+.*(print\(\|console\.log\|debugger;)'` |
| **Complexity guard** | Cyclomatic complexity bounded | `radon cc -nc src/` or enable ruff complexity rules |
| **Dead code guard** | No unused imports/variables | `ruff check src/` or `eslint --max-warnings 0` |
| **Security surface** | No secrets or sensitive literals in diff | `git diff \| grep -Ei '(password\|secret\|api_key\|token\|private_key)'` |

> **Note:** Do not commit these snippets as `.sh` files inside the project. Project stacks differ too much for one script to be universally correct. Copy the relevant lines into the spec's `## Verification` section and adjust them there.

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

## Change Trap Checklist

Unattended loops have predictable failure modes. Before claiming `<promise>DONE</promise>`, run through this checklist. Skip any item whose command does not apply to the current project stack.

| # | Trap | Why it happens | Quick check |
|---|---|---|---|
| 1 | **Assertions removed or weakened** | Agent makes failing tests pass by deleting expectations | `git diff -- tests/ \| grep -E '^-(\s*)(assert\|expect\|EXPECT_)'` |
| 2 | **Tests commented or skipped** | Agent bypasses failures instead of fixing them | `git diff -- tests/ \| grep -E '(^\+.*#.*test\|^\+.*@pytest\.mark\.skip\|^\+.*\.skip\()' && echo WARNING` |
| 3 | **Scope creep** | Agent "improves" adjacent code | `git diff --name-only` vs spec scope |
| 4 | **Lock/config files drift** | Agent adds dependencies or changes tool config | `git diff --stat pyproject.toml uv.lock package.json package-lock.json go.mod Cargo.lock` |
| 5 | **Debug leftovers** | `print`, `console.log`, `debugger`, `pdb` remain | `git diff --diff-filter=AM -U0 \| grep -E '^\+.*(print\(\|console\.log\|debugger;\|import pdb)'` |
| 6 | **TODO/FIXME in new code** | Agent defers work instead of finishing | `git diff --diff-filter=AM -U0 \| grep -E '^\+.*(TODO\|FIXME)'` |
| 7 | **Dead code increase** | Unused imports, variables, functions | `ruff check src/` or `eslint --max-warnings 0` |
| 8 | **Complexity spike** | Nested conditionals or long functions | `radon cc -nc src/` or ruff complexity rules |
| 9 | **Secrets or credentials** | Agent hardcodes tokens or passwords | `git diff \| grep -Ei '(password\|secret\|api_key\|token\|private_key\|aws_access_key_id)'` |
| 10 | **Existing behavior broken** | Change passes new tests but breaks old ones | Run the full test suite, not just the new test |

If any trap is triggered, do one of the following:
- Fix it and re-verify.
- If fixing it is outside the spec scope, document it in `## Blockers` and output `<promise>BLOCKED:...>`.
- If it requires human judgment, output `<promise>BLOCKED:needs-human-review`.

## Human Review Triggers

Even if all shell commands pass, output `<promise>BLOCKED:needs-human-review` instead of `<promise>DONE</promise>` when the spec touches:

- Authentication, authorization, or session handling
- Database schema or migrations
- Public API response format, status codes, or serialization
- External service integrations or network clients
- CI/CD, deployment, or secret-management configuration
- Any file outside the spec's stated scope
- Existing tests that were weakened, skipped, or commented out
- Backward-compatibility decisions that are ambiguous

When triggered:
1. Do NOT commit.
2. Add a `## Review Required` section to the spec explaining what needs human eyes and why.
3. Output `<promise>BLOCKED:needs-human-review`.

## Verification Pipeline Templates by Stack

Use these as starting points. Copy the relevant blocks into the spec's `## Verification` section and adjust paths/tools to the project.

### Python (uv / ruff / pytest)

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

### Node / TypeScript (npm / eslint / vitest)

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

### Go

```bash
go vet ./...
go test ./...
git diff --name-only
git diff --diff-filter=AM -U0 | grep -E '^\+.*(TODO|FIXME|fmt\.Print)'
```

### Rust

```bash
cargo check
cargo clippy -- -D warnings
cargo test
git diff --name-only
git diff --diff-filter=AM -U0 | grep -E '^\+.*(TODO|FIXME|println!)'
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

6. **Trusting the agent to self-grade**
   - Bad: Loop iteration reports "looks good" without running commands.
   - Good: Every claim is backed by a shell command in the log.

## Verification Checklist for Specs

Before finalizing a spec, ask:

- [ ] Can I run every criterion from the project root with one command?
- [ ] Does each criterion have a concrete expected output?
- [ ] Did I run the criterion before writing the spec to establish a baseline?
- [ ] Are pre-existing failures listed in `## Exclusions`?
- [ ] Is the fastest/cheapest check listed first?
- [ ] Do the criteria cover both "the change was made" and "nothing else broke"?
- [ ] Did I include at least one change-trap check?
- [ ] Did I list human-review triggers if the spec touches auth/DB/API/CI/secrets?

## Example Verification Section

```markdown
## Verification

Run these commands after each change and before claiming completion:

```bash
# 1. Static checks
uv run ruff check src/owloop tests/

# 2. Type checks
uv run mypy src/owloop

# 3. Scope discipline
git diff --name-only

# 4. Test integrity
git diff -- tests/ | grep -E '^-(\s*)(assert|expect)' && echo "WARNING"

# 5. Change-trap scan
git diff --diff-filter=AM -U0 | grep -E '^\+.*(TODO|FIXME|print\()'

# 6. Unit tests
uv run pytest tests/test_adapters.py -q
```

Expected results:
- `ruff`: 0 errors
- `mypy`: 0 errors
- `git diff --name-only`: only `src/owloop/adapters.py` and `tests/test_adapters.py`
- Test-integrity warning: empty
- Change-trap scan: empty
- `pytest`: all passed
```

## References

- [Automated Code Review Checklist](references/code-review-checklist.md)
