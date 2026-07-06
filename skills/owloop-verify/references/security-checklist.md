# Security Checklist

These checks are designed for an autonomous loop. Only include checks that can be expressed as runnable shell commands with deterministic output. For judgment-based security concerns, use [Human Review Triggers](human-review-triggers.md).

## Input/Output Safety

| Concern | Check |
|---|---|
| SQL/NoSQL/command injection | `grep -R "f\".*SELECT\|execute(.*%\|\.format(.*SELECT" src/` |
| Path traversal | `grep -R "open(.*\(.*\)\|Path(.*\+" src/` and review |
| Unsafe HTML | `grep -R "dangerouslySetInnerHTML\|innerHTML" src/` |
| Prototype pollution (JS) | `grep -R "Object.assign(.*req\.\|Object\.assign(.*JSON" src/` |

## Secrets and Sensitive Data

| Concern | Check |
|---|---|
| Hardcoded secrets in diff | `git diff \| grep -Ei '(password\|secret\|api_key\|token\|private_key\|aws_access_key_id)'` |
| Secrets in lock/config | `grep -R "sk-.*\|AKIA\|ghp_" . --include="*.json" --include="*.toml" --include="*.yaml"` |
| Excessive logging | `git diff --diff-filter=AM -U0 \| grep -Ei '^\+.*(password\|secret\|token\|ssn\|email)'` |

## AuthN/AuthZ (scope-dependent)

If the spec touches auth, add a human-review trigger rather than a shell gate. Machine-checkable signals:

| Signal | Check |
|---|---|
| Missing auth decorator | `grep -R "@require_auth\|@login_required" src/routes/ \| wc -l` vs baseline |
| New endpoint without guard | manual diff review |

## Runtime Risks

| Concern | Check |
|---|---|
| Unbounded loops | `grep -R "while True" src/owloop/ \| wc -l` — review each |
| Missing timeouts | `grep -R "requests\.get(.*timeout\|httpx\.get(.*timeout" src/ \| wc -l` vs new calls |
| Regex DoS | `grep -R "re\.match(.*(\*|re\.search(.*(\*" src/` — review |

## Spec-Level Criterion Template

```bash
# Secret scan on diff
git diff | grep -Ei '(password|secret|api_key|token|private_key|aws_access_key_id)' && echo "FAIL" || echo "OK"
```

Expected output: `OK`.

```bash
# No unsafe HTML/innerHTML in changed JS/TS
FILES=$(git diff --name-only --diff-filter=ACMR HEAD | grep -E '\.(js|ts|tsx)$' || true)
[ -z "$FILES" ] && exit 0
grep -R "dangerouslySetInnerHTML\|\.innerHTML" $FILES && echo "FAIL" || echo "OK"
```

Expected output: `OK`.

## Important Limitations

- This checklist catches **obvious patterns**, not subtle vulnerabilities.
- Any spec that adds auth, crypto, network clients, or secret handling should also add a **human review trigger**.
