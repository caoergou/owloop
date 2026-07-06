---
name: owloop-loop-control
description: >-
  Promise protocol and loop control for Owloop — teach an agent when to output
  <promise>DONE</promise>, <promise>BLOCKED:reason</promise>, or
  <promise>DECIDE:question</promise>, and how to behave when stuck.
  Use when the loop won't stop, the agent keeps retrying the same error,
  or you need to design convergence behavior for an autonomous run.
license: MIT
compatibility: Requires owloop methodology; works with any agentskills.io-compatible agent
metadata:
  author: caoergou
  version: "0.3.0"
  repository: https://github.com/caoergou/owloop
---

# Owloop Loop Control

Loop control is what separates a convergent autonomous run from an expensive infinite loop. This skill covers the Owloop **promise protocol**, **stuck behavior**, and **guardrails** that keep the loop on the rails.

## When to Use

Use this skill when:
- The user asks why a loop won't stop or keeps retrying
- You need to decide what `<promise>` signal to output
- A spec needs explicit stuck-behavior instructions
- The user wants to add guardrails (max tokens, max iterations, idle timeout)

## The Promise Protocol

The agent communicates completion state by outputting exactly one of these XML-like tags in its final response:

### `<promise>DONE</promise>`

Output this when:
- All acceptance criteria pass
- The verification commands run successfully
- The work is committed (or ready to commit)
- No human judgment is needed

This is the only signal that causes the loop to mark the spec complete and move on.

### `<promise>BLOCKED:reason</promise>`

Output this when:
- You cannot make progress due to an external blocker
- The blocker is outside the scope of the spec
- Continuing to retry would waste tokens

Examples:
- `<promise>BLOCKED:pytest crashes on import due to missing fixture in unrelated module</promise>`
- `<promise>BLOCKED:network required to fetch dependency, offline environment</promise>`

When blocked:
1. Add a `## Blockers` section to the spec describing the blocker
2. Commit any partial, safe progress
3. Output `<promise>BLOCKED:...</promise>`

### `<promise>DECIDE:question</promise>`

Output this when:
- The spec is ambiguous or contradictory
- A product/design decision is required
- Multiple valid implementations exist and the agent cannot choose

Examples:
- `<promise>DECIDE:should the new endpoint return 201 or 204 on success?</promise>`
- `<promise>DECIDE:should we keep backward compatibility or break the API?</promise>`

When deciding is needed:
1. State the question clearly
2. List the options and trade-offs
3. Output `<promise>DECIDE:...</promise>`
4. Do NOT pick an option yourself

## When NOT to Output a Promise Signal

Do not output a promise signal if:
- Acceptance criteria failed and you have not tried the stuck-behavior plan
- You are in the middle of implementation (only output at the end of an iteration)
- You are asking a clarifying question that is not a binary decision

## Stuck Behavior

Every spec should define what happens when the agent cannot make progress. If the spec doesn't define it, default to **document and move on**.

### Option 1: Document and move on (default)

> If you cannot make progress after 2 attempts at the same error, add a `## Blockers` section to this spec describing what's blocking you, commit your partial work, and output `<promise>DONE</promise>`.

Best for: most tasks, especially exploratory fixes.

### Option 2: Partial commit

> If only some acceptance criteria pass, commit the passing changes, update the acceptance criteria to reflect remaining work, and output `<promise>DONE</promise>`.

Best for: large cleanup tasks where partial progress is valuable.

### Option 3: Revert and stop

> If tests fail after implementation, `git checkout .` to revert all changes and output `<promise>DONE</promise>` with a note about what went wrong.

Best for: risky changes where a bad partial commit is worse than no commit.

## Fix-Loop Detection

A fix loop happens when the agent hits the same error and applies the same (or equivalent) fix repeatedly. Signs:
- The same file is modified in 3+ consecutive iterations
- The same test fails with the same error message
- The agent's "fix" is undoing a previous change

Prevention:
- Follow the stuck-behavior plan after 2 failed attempts at the same error
- Add the failure pattern to the spec's `## Blockers` section
- Do not retry the same command more than twice without changing strategy

## Guardrails

Use these controls to bound an unattended run. When using the owloop CLI, use the flags shown. When running manually via `owloop-runner`, enforce the same bounds in your loop header or loop log.

| Control | Generic bound | owloop CLI flag | Purpose |
|---|---|---|---|
| Max iterations | `max_iterations: 20` | `owloop run -n 20` | Stop after N specs/iterations |
| Max duration | `max_duration_minutes: 120` | `owloop run --max-duration 120` | Stop after N minutes |
| Max tokens | `max_tokens: 200000` | `owloop run --max-tokens 200000` | Stop before costs spiral |
| Idle timeout | `idle_timeout_seconds: 3600` | `owloop run --idle-timeout 3600` | Kill a stuck agent after N seconds |

Recommendation: always set at least one bound before running overnight.

## Loop Convergence Checklist

Before claiming `<promise>DONE</promise>`, verify:

- [ ] All acceptance criteria pass (run the commands, don't assume)
- [ ] No files outside scope were modified (check `git status`)
- [ ] Existing tests still pass (unless excluded)
- [ ] The change is committed or staged
- [ ] If stuck, the stuck-behavior plan was followed

## Anti-Patterns

1. **Self-graded homework**
   - Bad: "The code looks correct, so I'm done."
   - Good: "`uv run pytest` passes, so I output `<promise>DONE</promise>`."

2. **Ignoring pre-existing failures**
   - Bad: "Tests fail, but they failed before I started."
   - Good: "Pre-existing failures are listed in `## Exclusions`; my new tests pass."

3. **Scope creep**
   - Bad: "While fixing the lint error, I also refactored the database layer."
   - Good: "I only touched files listed in `## Requirements`; everything else is untouched."

4. **Infinite retry**
   - Bad: Running the same failing command 10 times hoping for a different result.
   - Good: After 2 failures, document the blocker and output `<promise>BLOCKED:...</promise>`.

## Related Skills

- **`owloop`** — Core loop engineering methodology.
- **`owloop-runner`** — How to enforce these controls when the owloop CLI is unavailable.
- **`owloop-verify`** — How to design the verification commands that must pass before outputting `<promise>DONE</promise>`.
