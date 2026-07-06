# Feature: feat: subagent orchestration in build iterations

## Priority: 3

## Requirements
## Problem

Currently each build iteration runs a single `claude -p` process that does everything: read specs, investigate code, implement changes, run tests, commit. This means:

- The context window fills with file contents from investigation, leaving less room for implementation
- No separation of concerns — the same agent reads, writes, and verifies
- No parallelism — investigation and implementation are sequential

## Proposal

Restructure each iteration into subagent phases, following the Ralph playbook pattern:

1. **Orient** — subagent reads spec + relevant source files, produces a focused implementation plan
2. **Implement** — subagent receives the plan + only the files it needs to modify
3. **Verify** — separate subagent runs acceptance criteria (see #1)
4. **Commit** — main agent commits if verify passes

Each subagent gets a fresh, focused context window instead of one overloaded window.

## Trade-offs

- **Pro**: Better context utilization, separation of concerns, enables parallel investigation
- **Con**: More API calls per iteration, more complex orchestration, higher total tokens
- **Mitigation**: Only use subagent mode for large specs (>3 files); small specs can stay single-agent

## References

> "Ralph requires a mindset of not allocating to the primary context window. Instead, spawn subagents." — [Geoffrey Huntley](https://ghuntley.com/ralph/)

> "Main agent coordinates. ClaudeFast's Code Kit implements this B-thread pattern with its /team-plan and /team-build pipeline." — [claudefa.st](https://claudefa.st/blog/guide/mechanics/autonomous-agent-loops)

## Implementation notes

This likely requires changes to `engine.py` (iteration orchestration) and `adapters.py` (multi-process management). Could be opt-in via `--subagents` flag initially.

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
