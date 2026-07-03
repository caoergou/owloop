# Spec Format Reference

Owloop specs are **constraint-oriented**: beyond requirements, they define boundaries (Exclusions) and evidence (shell-verifiable Acceptance Criteria) that keep an unattended loop from wandering.

## Template

```markdown
# Spec: [name]

## Priority: [1-5]

## Requirements
[What to build — the functional description]

## Acceptance Criteria
[Shell commands with expected output — this is how owloop determines "done"]

- [ ] `grep -c "except ValidationError" backend/app/api/*.py` → ≤ 5
- [ ] `uv run ruff check backend/` → 0 errors
- [ ] `uv run pytest tests/test_auth.py` → all pass

## Exclusions
[What NOT to do — be explicit. This keeps autonomous runs from wandering.]

- Do NOT modify files outside the scope described above
- Do NOT change any external API behavior
- Do NOT modify pyproject.toml, uv.lock, or other config files

## Style
[Coding conventions to follow]

- Follow the existing pattern in [file/module]

## Verification
[Exact commands to run after each change, before claiming completion]

\```bash
uv run ruff check backend/
uv run pytest
\```

Output when complete: `<promise>DONE</promise>`
```

## Best Practices

### Acceptance Criteria
- Every criterion must be a shell command with a concrete expected output
- Avoid subjective descriptions like "works correctly" or "is clean"
- Good: `grep -c "except ValidationError" backend/app/api/*.py → ≤ 5`
- Bad: "Error handling is properly unified"

### Exclusions (highest leverage)
- The single most important section for autonomous runs
- Without explicit exclusions, the agent WILL "improve" things outside scope
- List specific files, directories, and behaviors that must not change
- Common exclusions: database schema, public API shapes, config files, unrelated modules

### Priority
- `1` = blocking / urgent
- `3` = normal (default)
- `5` = nice-to-have
- Specs are processed in filename order (lexicographic), not by priority field

### Sizing
- One spec = one concern
- Ideal: 1-3 files, < 100 lines of change
- If a spec touches > 5 files or requires judgment calls, split it

### Naming Convention
- `001-extract-validation-error.md`
- `002-add-type-annotations.md`
- Number prefix determines processing order
- Keep padding consistent (all 2-digit or all 3-digit)

## What Works Well with Owloop

**Best fit (mechanical, verifiable):**
- Lint/type error fixes
- Dead code removal
- Extract repeated patterns (DRY)
- Add type annotations
- Import cleanup
- Code formatting standardization

**Good fit (structured, bounded):**
- Service layer extraction (with blueprint)
- Schema migration (Marshmallow → Pydantic)
- Error handling unification
- Log/print standardization

**Poor fit (requires judgment):**
- Feature design decisions
- Architecture changes without blueprint
- Performance optimization without clear metrics
- UI/UX decisions

**Rule of thumb:** If you can write a shell command that verifies "done", it's a good owloop task.
