# Feature: feat: spec quality review skill (code-review integration)

## Priority: 3

## Requirements
## Problem

Generated specs go directly to the user for approval. There's no automated quality gate between spec generation and loop execution. Common spec defects:

- Acceptance criteria that aren't actually runnable (`grep` pattern doesn't match, command not found)
- Exclusions that are too vague ("don't break things")
- Scope too large (touches 10+ files)
- Missing baselines (target set without measuring current state)

The existing `owloop check` (spec_linter.py) catches structural issues but cannot judge semantic quality.

## Proposal

After spec generation, run an automated quality review step:

1. **Static checks** (existing `SpecLinter`) — structure, format, required sections
2. **Executable checks** — actually run each acceptance criteria command to verify it works
3. **Agent review** — a separate agent reviews the spec for:
   - Unrealistic targets
   - Overlapping/conflicting exclusions and requirements
   - Missing edge cases
   - Scope creep signals

Auto-fix what can be fixed, flag the rest for user attention.

This integrates the code-review skill concept into the spec pipeline — reviewing specs, not code.

## Why this matters

> "You are not necessarily supposed to write all the specs manually... a special agent writes specs for you." — [Spec-Driven Development](https://www.abrahamberg.com/blog/spec-driven-development-and-the-ralph-loop-the-good-the-bad-and-the-ugly/)

But if the spec agent writes bad specs, the loop wastes tokens on impossible tasks.

## Acceptance Criteria
Candidate acceptance criteria derived from issue checklist items:

- [ ] TODO: shell command → expected output

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

If you cannot make progress after 2 attempts at the same error, add a `## Blockers`
section to this spec describing what's blocking you, commit your partial work, and
output `<promise>DONE</promise>`.

## Verification
[Exact commands to run after each change, before claiming completion]

```bash
[test command]
[lint command]
```

## Baseline
[Calibration data recorded before the loop started — helps track progress]

- [command]: [current value] → target [target value]

Output when complete: `<promise>DONE</promise>`
