# Spec: subagent-orchestration

Status: COMPLETE

## Priority: 4

## Depends On
- `03-separate-verifier-agent.md`

## Requirements
- [x] Add an opt-in `--subagents` flag to `owloop run`.
- [x] When enabled, split each large iteration (>3 touched files) into phases: Orient, Implement, Verify, Commit.
- [x] **Orient** subagent: reads spec + relevant source files, returns a focused implementation plan and file list.
- [x] **Implement** subagent: receives the plan and files, makes changes, and emits `<promise>DONE</promise>`.
- [x] **Verify** subagent: runs acceptance criteria independently (reuses verifier from #1).
- [x] **Commit** remains the main agent's responsibility after verification passes.
- [x] Small specs (≤3 files) keep the existing single-agent flow.

## Acceptance Criteria
- [x] `uv run pytest tests/test_subagents.py -q` → all passed.
- [x] Running `owloop run --subagents` with a large spec spawns Orient, Implement, and Verify subagents in order.
- [x] Running `owloop run` without `--subagents` keeps the current single-agent behavior.
- [x] Subagent failures surface clear error messages without corrupting the main workspace.

## Exclusions
- Do NOT make subagent mode the default.
- Do NOT change the existing adapter API contract for single-agent runs.
- Do NOT modify the worktree/commit logic beyond orchestration.

## Style
- Use the existing adapter spawning utilities in `src/owloop/adapters.py`.
- Keep phase boundaries explicit with clear prompts and result parsing.

## Stuck Behavior
If a subagent fails or stalls, escalate to the main agent with the subagent output and allow one retry before blocking.

## Verification
```bash
uv run pytest tests/test_subagents.py -q
uv run pytest tests/test_engine.py -q
```

## Baseline
- All work happens in one agent context per iteration.
- No phase separation exists.

Output when complete: `<promise>DONE</promise>`
