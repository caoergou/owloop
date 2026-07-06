# Human Review Triggers

Even if all shell commands pass, output `<promise>BLOCKED:needs-human-review` instead of `<promise>DONE</promise>` when the spec touches any of the following areas.

## Always trigger human review

- Authentication, authorization, or session handling
- Database schema or migrations
- Public API response format, status codes, or serialization
- External service integrations or network clients
- CI/CD, deployment, or secret-management configuration
- Cryptography, password hashing, or token generation

## Trigger when observed in the diff

- Any file outside the spec's stated scope
- Existing tests that were weakened, skipped, commented out, or deleted
- New runtime dependencies or dependency upgrades
- Lock files changed without explicit approval
- Configuration files that affect production behavior
- Performance-sensitive paths changed without benchmarks

## Trigger when the decision is ambiguous

- Backward-compatibility trade-offs
- Breaking changes vs. preserving legacy behavior
- API naming or resource modeling decisions
- Data retention or privacy implications

## Procedure when triggered

1. Do NOT commit.
2. Add a `## Review Required` section to the spec explaining what needs human eyes and why.
3. Output exactly:

   ```text
   <promise>BLOCKED:needs-human-review — changes touch [area] and require human approval before merge</promise>
   ```

## Example

```markdown
## Review Required

This spec changes the `users` table schema by adding a nullable `email_verified_at` column.
While the change is additive and backward-compatible, it touches database schema,
so it requires human review before merge.
```
