---
name: owloop
description: >-
  Core methodology for loop engineering — 规范驱动的自主编码循环核心方法论。
  Learn when to run autonomous coding loops, how to keep them convergent,
  and how to write specs that don't drift.
  Use when user mentions owloop, loop engineering, autonomous loop,
  spec-driven, overnight coding, 自主循环, 循环工程, 隔夜编码, 跑循环.
license: MIT
compatibility: Requires git and a CLI-based coding agent (Claude Code, Kimi Code CLI, Codex, Cursor, etc.)
metadata:
  author: caoergou
  version: "0.3.0"
  repository: https://github.com/caoergou/owloop
---

# Owloop

> **Language policy:** Respond in the user's language. Spec section headers in generated files are always English (`## Requirements`, `## Exclusions`, etc.).

Owloop is **loop engineering**: spec-driven development plus an autonomous coding loop. Each iteration spawns a fresh agent process against one spec, verifies acceptance criteria with shell commands, and commits only on success.

## When to Use

Use the owloop methodology when the user asks about:
- Running an autonomous coding loop overnight
- Writing specs for agent-driven development
- Keeping agent loops from drifting or looping forever
- owloop commands (`owloop init`, `owloop run`, `owloop spec`, etc.)

Also use for these task shapes:
- Mechanical improvements: lint fixes, type annotations, dead code removal
- Overnight unattended runs against well-defined tasks
- Anything where "done" can be expressed as a shell command

## When NOT to Use

- Tasks requiring product judgment or design decisions
- Security-sensitive changes
- Anything where "done" can't be expressed as a shell command
- Vague requests like "improve the code" or "make it better"

## Core Principles

1. **Constraint-oriented specs**
   - Define what's off-limits first (Exclusions).
   - Every acceptance criterion must be a shell command with a verifiable output.

2. **Fresh context per iteration**
   - Each loop round is a brand-new agent process.
   - State lives on disk (`.owloop/specs/`, `.owloop/logs/`, git history).

3. **Deterministic completion signal**
   - The agent outputs `<promise>DONE</promise>`.
   - The loop detects this with `grep`, not with an AI judgment call.

4. **Auto mode, not YOLO**
   - Use your agent's non-interactive auto-permission mode.
   - Never use dangerously-skip-permissions or equivalent YOLO modes.

5. **One concern per spec**
   - Ideal spec: 1-3 files, < 100 lines of change, 15-45 minutes per iteration.
   - If a spec touches > 5 files or needs sequential sub-steps, split it.

## Installation

Install the owloop Python CLI from PyPI:

```bash
uv tool install owloop
# or: pip install owloop
```

Install the companion skills for your agent:

```bash
# Claude Code
npx skills add caoergou/owloop --agent claude-code

# Kimi Code CLI / Codex / Cursor / etc.
npx skills add caoergou/owloop --agent '*'
```

## Quick Start

```bash
# Initialize in your project (creates only .owloop/)
owloop init

# Turn a vague goal into a concrete spec
owloop spec "refactor error handling"

# Or edit .owloop/specs/01-example.md manually, then run
owloop run
```

## The Loop

```
Loop iteration N:
  1. Pick highest-priority incomplete spec from .owloop/specs/
  2. Spawn fresh agent process with auto permission mode
  3. Agent implements spec and runs verification commands
  4. Agent outputs <promise>DONE</promise> on success
  5. Loop detects signal via grep (deterministic)
  6. Commit + push, move to next spec
```

## Commands

| Command | Description |
|---|---|
| `owloop init` | Initialize owloop in current project |
| `owloop spec "goal"` | Turn a vague goal into a concrete spec |
| `owloop run` | Start the autonomous loop |
| `owloop run --agent kimi` | Use Kimi Code CLI as the loop agent |
| `owloop check` | Pre-flight lint for specs |
| `owloop status` | Show specs and completion progress |
| `owloop report` | Generate HTML summary report |

## Related Skills

Use these companion skills for specific parts of the workflow:

- **`owloop-spec`** — Interactive wizard to create high-quality specs
- **`owloop-loop-control`** — Promise protocol (DONE/BLOCKED/DECIDE) and stuck behavior
- **`owloop-verify`** — Baseline calibration and verification pipeline design

## References

- [Loop Engineering Best Practices](references/loop-engineering-guide.md)
- [Comparison with /goal, gnhf, roborev](references/comparison.md)
- [Scenario: Legacy Refactoring](references/legacy-refactoring.md)
- [Scenario: ML / DS Code Hygiene](references/ml-engineering-hygiene.md)
- [Scenario: API / Framework Migration](references/api-migration.md)

## Links

- **GitHub:** https://github.com/caoergou/owloop
- **Original methodology:** [Geoffrey Huntley's Ralph Wiggum](https://ghuntley.com/ralph/)
- **Forked from:** [fstandhartinger/ralph-wiggum](https://github.com/fstandhartinger/ralph-wiggum)
