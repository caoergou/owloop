# Loop Engineering Best Practices

Synthesis of best practices from Geoffrey Huntley, Steve Kinney, Anthropic, Addy Osmani, and the broader loop engineering community.

## The Critical Formula

> "The single biggest predictor of whether Ralph-style automation works is whether you can finish the sentence 'this is done when X passes.' If you can't, you're asking the loop to make a judgment call it's structurally incapable of making."
> — Gen Alpha AI

## Pre-flight Checklist

Before writing any spec, these questions must all be "yes":

1. **"Can I express 'done' as a shell command that returns pass/fail?"** — If not, the loop cannot know when to terminate.
2. **"Can I verify the output in under 2 minutes in the morning?"** — If not, the task is too vague or too large.
3. **"Can a test/linter/build reject bad output?"** — If not, the agent grades its own homework.
4. **"Is this one clear outcome, one bounded area, one testable condition?"** — Oversized tasks cause drift.

## Baseline Calibration

Run acceptance criteria commands BEFORE the loop starts. This catches:

- **Already-passing specs** — the loop would exit instantly on iteration 1 without doing real work
- **Broken infrastructure** — `pytest` fails because of a missing fixture, so the loop can NEVER pass
- **Unmeasurable criteria** — the command doesn't actually output what you expected

Example calibration:
```bash
# Proposed acceptance criterion: "ruff errors ≤ 5"
$ uv run ruff check backend/ 2>&1 | tail -1
Found 84 errors.
# Baseline: 84 → target ≤ 5 is achievable but large. Consider splitting.
```

## Task Sizing

The sweet spot is **15-45 minutes per spec iteration**:

| Size | Risk | Action |
|---|---|---|
| < 15 min | Spec overhead > implementation time | Batch with related tasks or just do it interactively |
| 15-45 min | Ideal | Write the spec |
| 45-90 min | Context window may fill; agent may lose focus | Split into 2-3 specs with dependencies |
| > 90 min | Almost certainly will loop or drift | Decompose into independent pieces |

Indicators a spec is too large:
- Touches more than 5 files
- Has more than 5 acceptance criteria
- Requires sequential sub-steps ("first do A, then B, then C")
- Contains the word "and" more than twice in the requirements

## Stuck Behavior

Every spec should define what happens when the agent can't make progress. Without this, a stuck agent retries the same failed approach forever.

Options (pick one per spec):
- **Document and move on:** "If you cannot make progress after 2 attempts, add a `## Blockers` section to this spec describing what's blocking you, commit what you have, and output `<promise>DONE</promise>`."
- **Partial commit:** "If only some acceptance criteria pass, commit the passing changes, mark the spec as `Status: PARTIAL`, and output `<promise>DONE</promise>`."
- **Hard stop:** "If tests fail after implementation, revert all changes and output `<promise>DONE</promise>` with a note in the spec about what went wrong."

## Common Failure Modes

### 1. Vague acceptance criteria
- Bad: "Auth flow is correct"
- Good: `curl -s -o /dev/null -w "%{http_code}" localhost:8000/api/auth/expired-token` → `401`

### 2. Missing exclusions → scope creep
The agent "helpfully" refactors the database layer while fixing a lint error.
- Prevention: Explicit "do NOT touch" list. Be specific about files and behaviors.

### 3. Fix loops (same error N times)
The agent hits an error, tries the same fix, fails, repeats identically.
- Prevention: Stuck behavior instructions. Fix-loop detection (owloop v0.2+ has this built in).

### 4. Agent weakens tests to make them pass
The agent removes or comments out failing tests instead of fixing the code.
- Prevention: Add to exclusions: "Do NOT modify, delete, or comment out existing tests."

### 5. Agent assumes code doesn't exist
The agent re-implements something that's already in the codebase.
- Prevention: Add to requirements: "Before implementing, search the codebase for existing implementations."

### 6. Premature completion
The agent reports done when it isn't.
- Prevention: Shell-verifiable acceptance criteria (not self-assessment). owloop uses `grep` for `<promise>DONE</promise>`, not AI judgment.

## The Tuning Process

From Huntley: tune specs "like a guitar" — observe and adjust reactively:

1. Watch the first 2-3 iterations attended
2. When the agent fails in a specific way, add a constraint to prevent it
3. The codebase itself steers: add correct patterns as examples for the next fresh-context iteration
4. Encode every failure as a rule — the constraint file gets longer, failures get fewer

## Sources

- Geoffrey Huntley — https://ghuntley.com/ralph/
- Steve Kinney — https://stevekinney.com/writing/the-ralph-loop
- Addy Osmani — https://addyosmani.com/blog/loop-engineering/
- Anthropic — https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- Saulius — https://saulius.io/blog/loop-engineering-systems-that-drive-agents
- Codecentric — https://www.codecentric.de/en/knowledge-hub/blog/the-ralph-wiggum-loop-autonomous-code-generation-with-a-fresh-context
