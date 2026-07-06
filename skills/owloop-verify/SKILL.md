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
  version: "0.4.0"
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

## The Golden Rule

Every acceptance criterion must be a **runnable shell command with a concrete expected output**.

- Good: `uv run pytest tests/test_auth.py -q` → `1 passed`
- Good: `grep -c "except ValidationError" backend/app/api/*.py` → `≤ 5`
- Bad: "Error handling is properly unified"
- Bad: "The code works correctly"

For detailed guidance on writing criteria, see [Writing Acceptance Criteria](references/writing-criteria.md).

## Baseline Calibration

Run the proposed verification command BEFORE the loop starts. Record the current state and set a realistic target.

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

## Change Traps and Human Review

Unattended loops have predictable failure modes. Before claiming completion, consult:

- [Change Trap Checklist](references/change-trap-checklist.md) — 10 common drift patterns and how to detect them.
- [Human Review Triggers](references/human-review-triggers.md) — when to stop and ask a human, even if all commands pass.

## Pipeline Templates by Stack

For ready-to-use verification blocks, see [Pipeline Templates](references/pipeline-templates.md).

## Verification Checklist for Specs

Before finalizing a spec, ask:

- [ ] Can I run every criterion from the project root with one command?
- [ ] Does each criterion have a concrete expected output?
- [ ] Did I run the criterion before writing the spec to establish a baseline?
- [ ] Are pre-existing failures listed in `## Exclusions`?
- [ ] Is the fastest/cheaptest check listed first?
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

- [Writing Acceptance Criteria](references/writing-criteria.md)
- [Change Trap Checklist](references/change-trap-checklist.md)
- [Human Review Triggers](references/human-review-triggers.md)
- [Pipeline Templates](references/pipeline-templates.md)
