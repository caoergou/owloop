---
name: owloop-runner
description: >-
  Run an Owloop autonomous coding loop without the owloop CLI.
  Teaches a coding agent how to act as its own loop runner: discover specs,
  spawn iterations, parse promise signals, commit progress, and stop safely.
  Use when owloop CLI is unavailable, the user says "run the loop manually",
  or you need an agent-agnostic fallback for executing specs.
license: MIT
compatibility: Requires owloop methodology; works with any agentskills.io-compatible agent
metadata:
  author: caoergou
  version: "0.1.0"
  repository: https://github.com/caoergou/owloop
---

# Owloop Manual Runner

The owloop Python CLI is the recommended way to run an autonomous loop, but the methodology does not depend on it. This skill teaches a coding agent how to **act as its own runner** when the CLI is not installed, not available, or when the user explicitly wants a manual loop.

## When to Use

Use this skill when:
- The user asks you to "run the owloop loop" but `owloop` is not installed.
- The user says "run these specs manually" or "execute the spec queue yourself".
- You are working in an agent that cannot shell out to the owloop CLI.
- You need a fallback because `owloop run` failed or is not supported on this platform.

## When NOT to Use

- Do not use if the owloop CLI is available and the user asked for `owloop run` — prefer the CLI.
- Do not use for one-off tasks that are simpler to do interactively.

---

## Prerequisites

Before starting, confirm:

1. This directory is a git repository.
2. There is a `.owloop/specs/` directory with at least one `.md` spec file.
3. You have permission to run shell commands and make commits.
4. The agent is in a non-interactive / auto-permission mode (e.g., `--permission-mode auto` for Claude Code, or equivalent).

If any prerequisite is missing, stop and report `<promise>BLOCKED:...>`.

---

## The Manual Loop

```
Loop iteration N:
  1. Discover specs in .owloop/specs/
  2. Pick the highest-priority incomplete spec
  3. Build a fresh iteration prompt from the spec
  4. Execute the iteration (run commands, edit files, verify)
  5. Parse the final response for a <promise> signal
  6. If DONE: commit, push, mark spec COMPLETE, continue
  7. If BLOCKED/DECIDE: stop and report to user
  8. If no signal or failure: retry with backoff, or stop after max retries
```

---

## Step 1: Discover Specs

List spec files and identify which are incomplete:

```bash
find .owloop/specs -maxdepth 1 -type f -name '*.md' | sort
```

A spec is **incomplete** unless its markdown contains:

```markdown
**Status**: COMPLETE
```

near the top of the file (before `## Requirements`).

If all specs are complete, stop and report:

```
All specs complete. No further iterations needed.
<promise>DONE</promise>
```

---

## Step 2: Pick the Highest-Priority Spec

For each incomplete spec, read the frontmatter and find `## Priority`:

```markdown
## Priority: 1
```

Pick the spec with the **lowest priority number** (1 is highest). If two specs have the same priority, pick the one with the lower filename number (e.g., `001-xxx.md` before `002-xxx.md`).

Record your choice in the loop log:

```
Iteration N: picked <spec-filename>
```

---

## Step 3: Build the Iteration Prompt

Construct a prompt that contains:

1. **Context files** (if they exist):
   - `AGENTS.md`
   - `CLAUDE.md`
   - `.owloop/learnings.md`
   - `run-notes.md`
   - `STEERING.md`

2. **The spec content**:
   - Copy the entire spec file text.

3. **Explicit instructions**:

   ```markdown
   You are executing one iteration of an Owloop autonomous loop.

   Read the spec above carefully. Your job:
   1. Implement only what is in `## Requirements`.
   2. Do NOT touch anything in `## Exclusions`.
   3. Follow `## Style` conventions.
   4. Run every command in `## Verification` and confirm it produces the expected output.
   5. If you get stuck, follow `## Stuck Behavior`.
   6. When all acceptance criteria pass and no human-review trigger applies,
      add `**Status**: COMPLETE` near the top of this spec file,
      stage and commit your changes with a concise message,
      push if a remote exists,
      and output exactly `<promise>DONE</promise>`.
   7. If you are blocked by something outside this spec, output `<promise>BLOCKED:reason</promise>`.
   8. If you need a human decision, output `<promise>DECIDE:question</promise>`.
   ```

---

## Step 4: Execute the Iteration

How you execute the prompt depends on the agent you are running in.

### Option A: You are the runner and the worker in the same session

If the agent runtime supports continuing the same session, simply process the iteration prompt yourself: read files, run commands, edit code, verify, and emit the promise signal.

### Option B: Spawn a fresh agent subprocess

If your runtime allows spawning a subprocess with a prompt, use the agent's non-interactive prompt mode. Examples:

| Agent | Invocation | Notes |
|---|---|---|
| Claude Code | `claude -p --permission-mode auto --model claude-sonnet-5` | Pass prompt via stdin. Supports `--output-format stream-json`. |
| Kimi Code CLI | `kimi --prompt "..." --output-format stream-json` | `--prompt` cannot be combined with `--auto`; permission mode is controlled by Kimi config (`default_permission_mode: auto`). |
| Codex | `codex -p` or `codex --prompt` | Check `codex --help` for the current flag name. |
| Cursor | Cursor is primarily IDE-based; run the loop inside the agent session. | Use Option A. |

> **Important:** Never use YOLO / dangerously-skip-permissions modes. Always prefer `--permission-mode auto` or the agent's equivalent.

If you cannot spawn a subprocess and cannot act as the worker yourself, stop and report:

```
<promise>BLOCKED:agent runtime cannot execute iteration prompts</promise>
```

---

## Step 5: Parse the Promise Signal

After the iteration finishes, search the output for exactly one of:

```xml
<promise>DONE</promise>
<promise>BLOCKED:reason</promise>
<promise>DECIDE:question</promise>
```

Use a literal grep-like search. Do not interpret the output with an AI judgment call.

---

## Step 6: Handle DONE

If the signal is `DONE`:

1. Verify that the spec file now contains `**Status**: COMPLETE`.
2. Check `git status` to see what changed.
3. If the changes are reasonable and within scope, commit:
   ```bash
   git add -A
   git commit -m "feat: <spec-short-name>"
   ```
4. Push if a remote exists:
   ```bash
   git push origin $(git branch --show-current)
   ```
5. Log the iteration result.
6. Continue to the next spec.

If the iteration claimed DONE but did not actually mark the spec COMPLETE, treat it as a failure and retry.

---

## Step 7: Handle BLOCKED or DECIDE

If the signal is `BLOCKED` or `DECIDE`:

1. Do NOT commit or push.
2. Log the payload.
3. Stop the loop.
4. Report to the user:
   - Which spec was being worked on
   - The exact `<promise>` signal
   - Relevant log tail

Wait for human input before continuing.

---

## Step 8: Handle Failure or Missing Signal

If the iteration exits with an error or no promise signal:

1. Log the failure.
2. Increment a consecutive-failure counter.
3. If the counter reaches 3, stop the loop and report:
   ```
   <promise>BLOCKED:iteration failed 3 times for <spec-name></promise>
   ```
4. Otherwise, wait briefly (exponential backoff: 5s, 10s, 20s, max 60s) and retry the same spec.

---

## Guardrails

Always set at least one bound before running unattended:

| Bound | How to enforce |
|---|---|
| Max iterations | Stop after N specs/iterations |
| Max duration | Stop after N minutes |
| Max tokens | Track token usage per iteration and stop at a budget |
| Idle timeout | Kill an iteration if it produces no output for N seconds |
| Fix-loop detection | Stop if the same set of files is modified 3+ rounds without progress |

Example loop header to track:

```markdown
# Manual Loop Run
- Started: 2026-07-06 10:00:00
- Max iterations: 20
- Max duration: 120 minutes
- Max tokens: 200000
- Current iteration: 0
```

Update this header each round.

---

## State Management

Keep loop state on disk, not in context:

| State | Location | Purpose |
|---|---|---|
| Spec queue | `.owloop/specs/*.md` | Source of truth for what to do |
| Spec completion | `**Status**: COMPLETE` inside each spec | Marker to skip completed work |
| Learnings | `.owloop/learnings.md` | Facts discovered across iterations |
| Run notes | `run-notes.md` | Per-run iteration summaries |
| Loop log | `.owloop/logs/manual_runner_<timestamp>.log` | Structured loop events |

Do not rely on memory across iterations. If you crash or are restarted, reconstruct state from these files.

---

## Worktree Isolation

If possible, run the loop in a separate git worktree so the main checkout stays clean:

```bash
git worktree add ../$(basename $(pwd))-owloop-wt -b owloop/$(date +%Y%m%d)
cd ../$(basename $(pwd))-owloop-wt
```

Copy `.owloop/` and `.claude/` or `.agents/` into the worktree if needed. If worktrees are not possible, at minimum run on a dedicated branch.

---

## Anti-Patterns

1. **Letting the worker grade its own homework**
   - Bad: Worker says "looks good" and you trust it.
   - Good: Worker must run commands from `## Verification` and show outputs.

2. **Accumulating context across iterations**
   - Bad: Summarizing previous iterations from memory.
   - Good: Reading `run-notes.md` and `.owloop/learnings.md` at the start of each iteration.

3. **Ignoring scope**
   - Bad: Committing files outside the spec's Requirements.
   - Good: Running `git diff --name-only` before every commit.

4. **Infinite retry**
   - Bad: Running the same failing iteration 10 times.
   - Good: Stopping after 3 consecutive failures and asking for help.

---

## Example Minimal Manual Loop Log

```markdown
# Manual Owloop Run Log

## Run Configuration
- Max iterations: 10
- Max duration: 90 minutes
- Worktree: ../myproject-owloop-wt

## Iteration 1
- Spec: 001-fix-banner
- Result: DONE
- Commit: `a1b2c3d fix: update banner copy`
- Notes: none

## Iteration 2
- Spec: 002-extract-validator
- Result: BLOCKED:pytest crashes on import due to missing fixture
- Action: stopped, waiting for user
```

---

## Related Skills

- **`owloop`** — Core methodology and when to use the loop.
- **`owloop-spec`** — How to write specs that converge.
- **`owloop-loop-control`** — Promise protocol and stuck behavior.
- **`owloop-verify`** — How to design verifiable acceptance criteria and change-trap checks.
- **`owloop-report`** — How to generate a summary report from loop state.
