# Feature: feat: separate verifier agent from executor agent

## Priority: 3

## Requirements
## Problem

Currently owloop trusts the executing agent to self-report completion via `<promise>DONE</promise>`. The agent decides when to emit the promise — this is formal determinism but not actual verification.

Community's strongest consensus: **the agent that writes code should NOT judge whether it's done.**

> "The single most useful structural move in a loop is separating the agent that writes code from the agent that checks it." — [Loop Engineering overview](https://www.i-scoop.eu/loop-engineering/)

## Proposal

After each iteration's `<promise>DONE</promise>`, the engine spawns a **separate verification agent** that:
1. Reads the spec's acceptance criteria
2. Actually runs each shell command
3. Checks the output matches expected results
4. Returns pass/fail independently

Only if the verifier passes does the iteration count as complete.

## Why this matters

- Prevents premature completion (the #1 failure mode in autonomous loops)
- Catches cases where the agent commits code that doesn't actually pass
- Aligns with `/goal` pattern (separate evaluator model)

## References

- [AgentPatterns: Goal Contract](https://agentpatterns.ai/agent-design/goal-contract-completion-evaluator/)
- [PostHog: WTF is loop engineering](https://posthog.com/newsletter/loops)
- [Geoffrey Huntley: Ralph methodology](https://ghuntley.com/ralph/)

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
