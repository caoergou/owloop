# Feature: feat: AGENTS.md self-learning and recovery strategies

## Priority: 3

## Requirements
## Problem

Two gaps in owloop's learning/recovery mechanisms:

### 1. No AGENTS.md self-update
When the agent discovers operational knowledge during a run (e.g. "this project uses poetry not pip", "tests require a running database"), that knowledge dies with the iteration. The next iteration rediscovers it from scratch.

The Ralph methodology explicitly calls for the agent to update AGENTS.md with operational learnings:
> "The @AGENT.md is the heart of the loop. If Ralph discovers a learning, permit him to self-improve." — Huntley

### 2. Fix-loop detection without recovery
owloop detects death spirals (same files modified 3+ rounds) but only warns. It should:
- Auto-split the current spec into smaller pieces
- Or switch strategy (e.g. revert and try a different approach)
- Or escalate with `<promise>BLOCKED:...>`

## Proposal

1. Add a `## Operational Learnings` section to the build prompt that instructs the agent to append discoveries to `.owloop/learnings.md`
2. Load learnings into the next iteration's context (like run-notes.md)
3. On fix-loop detection: auto-generate a "split this spec" sub-task instead of just warning

## References

- [Ralph Playbook: Update AGENTS.md](https://github.com/moule3053/ralph-playbook)
- [Spec-Driven Development](https://www.abrahamberg.com/blog/spec-driven-development-and-the-ralph-loop-the-good-the-bad-and-the-ugly/)

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
