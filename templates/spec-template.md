# Feature: [name]

## Priority: [1-5]

## Files
[The files/directories this spec is allowed to touch, one per line — paths or
globs. This scope is what lets `owloop run --workers N` schedule this spec
alongside others whose scopes don't overlap. Omit it and the spec runs alone.]

- src/[module]/
- tests/test_[module].py

## Requirements
[What to build — the functional description of the feature. EARS-style phrasing
maps cleanly onto shell-verifiable criteria: "WHEN <trigger>, THE SYSTEM SHALL
<response>", "WHILE <state>, THE SYSTEM SHALL <response>", "IF <condition> THEN
THE SYSTEM SHALL <response>".]

## Acceptance Criteria
[Specific, testable criteria. Prefer exact shell commands with the expected output over vague statements.]

- [ ] `[command]` → [expected output]
- [ ] `[command]` → [expected output]

## Exclusions
[What NOT to do — be explicit. This is what keeps an autonomous run from wandering.]

- Do not modify [file/module]
- Do not change [behavior]

## Style
[Coding conventions to follow so generated code matches the existing codebase]

- Follow the existing pattern in [file/module]
- [Naming/formatting/library conventions]

## Stuck Behavior
[What to do if the agent cannot make progress]

If you cannot make progress after 2 attempts at the same error, do not commit or
claim completion. Output `<promise>BLOCKED:reason</promise>` (external blocker) or
`<promise>DECIDE:question</promise>` (needs a human decision) so the loop stops for
guidance. The loop owns git and marks specs complete — you never commit or add a
`Status: COMPLETE` line yourself.

## Verification
[Exact commands the loop re-runs to decide pass/fail — must be runnable outside
your edits. Do not modify this section or the Acceptance Criteria mid-iteration.]

```bash
[test command]
[lint command]
```

## Baseline
[Calibration data recorded before the loop started — helps track progress]

- [command]: [current value] → target [target value]

Output when complete: `<promise>DONE</promise>`
