# Change Trap Checklist

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
