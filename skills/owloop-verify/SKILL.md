---
name: owloop-verify
description: >-
  Verification pipeline design for Owloop — how to write shell-verifiable
  acceptance criteria, calibrate baselines, build a multi-layer verification
  chain, and add machine-checkable quality gates that an autonomous loop can
  evaluate deterministically.
  Use when a spec's acceptance criteria are vague, the loop can't tell if
  it's done, or you need to design or review a verification pipeline.
license: MIT
compatibility: Requires owloop methodology; works with any agentskills.io-compatible agent
metadata:
  author: caoergou
  version: "0.5.0"
  repository: https://github.com/caoergou/owloop
---

# Owloop Verification

Verification is the keystone of loop engineering. If "done" cannot be checked by a shell command, the loop cannot terminate reliably.

This skill is the entry point. Detailed reference material lives in the `references/` folder so it can be loaded only when needed.

## When to Use

Use this skill when:
- A spec's acceptance criteria are vague or subjective
- The loop exits without doing real work (already-passing criteria)
- The loop can never pass (broken infrastructure or impossible targets)
- You need to design a verification pipeline for a new project
- You want to review an existing spec's criteria before starting the loop

## The Golden Rule

Every acceptance criterion must be a **runnable shell command with a concrete expected output**.

- Good: `uv run pytest tests/test_auth.py -q` → `1 passed`
- Good: `grep -c "except ValidationError" backend/app/api/*.py` → `≤ 5`
- Bad: "Error handling is properly unified"
- Bad: "The code works correctly"

For detailed guidance on writing criteria, see [Writing Acceptance Criteria](references/writing-criteria.md).

## Severity Levels for Criteria

Not every check blocks completion. Classify each criterion so the loop knows what to enforce:

| Level | Name | Action if failed | Example |
|---|---|---|---|
| **P0** | Critical / Blocker | Loop must stop; spec is not done | New test fails, type checker errors, security secret committed |
| **P1** | Required | Must pass before `<promise>DONE</promise>` | New functionality tests, scope discipline |
| **P2** | Strongly preferred | Should pass; document in `## Blockers` if waived | Code complexity threshold, coverage drop |
| **P3** | Advisory | Nice-to-have; loop may proceed | Style suggestions, refactor recommendations |

In an autonomous loop, **only P0 and P1 checks are hard gates**. P2/P3 become human-review triggers.

## Workflow

### 1) Scope the Change

- Read the spec's `## Requirements` and `## Exclusions`.
- Use `git diff --name-only` after the first loop iteration to confirm changed files match the scope.
- If the diff touches files outside the spec scope, treat it as a P1 failure or human-review trigger.

### 2) Calibrate the Baseline

Run the proposed verification command **before** the loop starts. Record the current state and set a realistic target.

| Baseline finding | What it means | Action |
|---|---|---|
| Command already passes | Spec will exit on iteration 1 with no work done | Make the criterion stricter or pick a different task |
| Command crashes | Loop can never pass | Fix infrastructure first, or exclude the broken part |
| Baseline is far from target | Target is unrealistic | Split into smaller specs or adjust target |
| Pre-existing failures unrelated to scope | Spec is doomed | Exclude them explicitly |

See [Baseline Calibration](references/baseline-calibration.md) for step-by-step examples.

### 3) Design the Verification Pipeline

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

See [Pipeline Templates](references/pipeline-templates.md) for ready-to-use blocks by stack.

### 4) Add Machine-Checkable Quality Gates

Code review and verification overlap: both ask "is this change good enough to merge?" The difference is that verification checks functional correctness, while code review checks engineering quality. In an unattended loop, **only the machine-checkable parts of code review can become gates**.

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

For deeper checklists, see:
- [Linter Zero-New-Violations Checklist](references/linter-checklist.md)
- [Architecture Checklist](references/architecture-checklist.md)
- [Security Checklist](references/security-checklist.md)
- [Code Quality Checklist](references/code-quality-checklist.md)
- [Change Trap Checklist](references/change-trap-checklist.md)

### 5) Handle Pre-Existing Debt

If the project already has linter errors, test failures, or lint debt, do not let them doom the spec:

1. Record the baseline count in the spec's `## Baseline` section.
2. Write criteria as "no new violations" or "count ≤ baseline" rather than "count = 0".
3. List unrelated failing files in `## Exclusions`.

See [Linter Zero-New-Violations Checklist](references/linter-checklist.md) for the diff-based baseline strategy.

### 6) Stop for Human Review When Needed

Even if all shell commands pass, output `<promise>BLOCKED:needs-human-review` instead of `<promise>DONE</promise>` when the spec touches sensitive areas. See [Human Review Triggers](references/human-review-triggers.md).

## Output Format for a Verification Design

When asked to design or review a verification pipeline, structure your response as:

```markdown
## Verification Design Summary

**Spec**: [filename or issue]
**P0/P1 hard gates**: [count]
**P2/P3 advisory checks**: [count]
**Estimated runtime**: [fast / medium / slow]

---

## Baseline

| Criterion | Current | Target | Notes |
|---|---|---|---|
| `uv run pytest tests/test_x.py -q` | 0 passed | 1 passed | New test to be added |
| `uv run ruff check src/` | 12 errors | ≤ 12 errors | No new errors allowed |

---

## Verification Pipeline

### 1. Static checks
```bash
uv run ruff check src/ tests/
uv run mypy src/
```
Expected: 0 errors.

### 2. Scope & change-trap checks
```bash
git diff --name-only
git diff -- tests/ | grep -E '^-(\s*)(assert|expect)' && echo "WARNING"
git diff --diff-filter=AM -U0 | grep -E '^\+.*(TODO|FIXME|print\()'
```
Expected: only files in scope; no weakened assertions; no TODO/FIXME/print.

### 3. Unit tests
```bash
uv run pytest tests/test_x.py -q
```
Expected: 1 passed.

---

## Human Review Triggers

- [ ] Touches authentication / authorization
- [ ] Touches database schema or migrations
- [ ] Adds or upgrades dependencies

## Notes

[Any special considerations, exclusions, or follow-up specs]
```

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
- [ ] Are the criteria classified as P0/P1/P2/P3 so the loop knows what is mandatory?

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

| File | Purpose |
|------|---------|
| [Writing Acceptance Criteria](references/writing-criteria.md) | How to write runnable, deterministic criteria |
| [Baseline Calibration](references/baseline-calibration.md) | Establish realistic targets before the loop starts |
| [Pipeline Templates](references/pipeline-templates.md) | Ready-to-use verification blocks by stack |
| [Linter Zero-New-Violations Checklist](references/linter-checklist.md) | Run linters only on changed lines and classify findings |
| [Architecture Checklist](references/architecture-checklist.md) | Machine-checkable SOLID, coupling, and code-smell gates |
| [Security Checklist](references/security-checklist.md) | Security gates suitable for shell verification |
| [Code Quality Checklist](references/code-quality-checklist.md) | Error handling, performance, boundary conditions |
| [Change Trap Checklist](references/change-trap-checklist.md) | 10 common loop drift patterns and how to detect them |
| [Human Review Triggers](references/human-review-triggers.md) | When to stop and ask a human, even if all commands pass |
