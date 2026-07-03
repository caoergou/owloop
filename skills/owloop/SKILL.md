---
name: owloop
description: >-
  Spec-driven autonomous coding loop for Claude Code — 规范驱动的自主编码循环。
  Write constraint-oriented specs with shell-verifiable acceptance criteria,
  run the loop overnight, wake up to verified commits.
  Use when user mentions owloop, autonomous loop, spec-driven, overnight coding,
  loop engineering, 自主循环, 写 spec, 跑循环, 无人值守, 循环工程, 隔夜编码.
license: MIT
compatibility: Requires Python 3.10+, git, and Claude Code CLI
metadata:
  author: caoergou
  version: "0.2.0"
  repository: https://github.com/caoergou/owloop
---

# Owloop

> **Language policy:** Respond in the user's language. If the user writes in Chinese, respond entirely in Chinese. If in English, respond in English. Section headers in generated spec files are always English (`## Requirements`, `## Exclusions`, etc.).

Owloop is a **loop engineering** tool: it combines spec-driven development with an autonomous coding loop for Claude Code. Each iteration spawns a fresh `claude -p` process against one spec, verifies acceptance criteria with shell commands, and commits only on success.

## When to Use

- Mechanical improvements: lint fixes, type annotations, dead code removal, error handling unification
- Overnight unattended runs against a backlog of well-defined tasks
- Any task where "done" can be expressed as a shell command
- When `/goal` stops early because the Haiku evaluator misjudges completion

## When NOT to Use

- Tasks requiring product judgment or design decisions
- Security-sensitive changes
- Anything where "done" can't be expressed as a shell command

## Quick Start

```bash
# Install
uv tool install git+https://github.com/caoergou/owloop

# Initialize in your project
owloop init

# Edit the example spec, then run
owloop run
```

## Core Architecture

```
Loop iteration N:
  1. Pick highest-priority incomplete spec from specs/
  2. Spawn fresh `claude -p --permission-mode auto` (zero accumulated context)
  3. Agent implements spec, runs verification commands
  4. Agent outputs <promise>DONE</promise> on success
  5. Loop detects signal via grep (deterministic, not AI judgment)
  6. Commit + push, move to next spec
```

**Key properties:**
- **Fresh context every iteration** — no context overflow, no degradation
- **State on disk** — `specs/`, `IMPLEMENTATION_PLAN.md`, `logs/`
- **Auto Mode** — `--permission-mode auto`, never YOLO
- **Worktree isolation** — runs in a separate `git worktree`, main checkout untouched
- **Stuck detection** — 3 consecutive failures triggers warning and reset
- **Fix-loop detection** — same files modified 3+ rounds warns of possible death spiral
- **Duration cap** — `--max-duration` prevents overnight cost runaway

## Commands

| Command | Description |
|---|---|
| `owloop init` | Initialize owloop in current project (creates `specs/`, templates) |
| `owloop run` | Start the autonomous loop with TUI |
| `owloop run -n 20` | Limit to 20 iterations |
| `owloop run --max-duration 120` | Stop after 2 hours |
| `owloop plan` | Generate implementation plan from specs |
| `owloop status` | Show specs and completion progress |

## Writing Specs

The spec format is **constraint-oriented**: define what's off-limits, then make every acceptance criterion a shell command. See [references/spec-format.md](references/spec-format.md) for the complete template and examples.

Key sections:
- **Requirements** — what to build
- **Acceptance Criteria** — `command → expected output` (shell-verifiable)
- **Exclusions** — what NOT to touch (highest-leverage section for preventing drift)
- **Style** — conventions to follow
- **Verification** — exact commands to run before claiming completion

## Loop Engineering Best Practices

See [references/loop-engineering-guide.md](references/loop-engineering-guide.md) for the full guide on writing specs that converge, baseline calibration, task sizing, stuck behavior, and common failure modes.

## Scenario References

When the user's task matches one of these scenarios, read the corresponding reference before writing or executing a spec:

- **Legacy refactoring** → read [references/legacy-refactoring.md](references/legacy-refactoring.md)
- **ML / DS code hygiene** → read [references/ml-engineering-hygiene.md](references/ml-engineering-hygiene.md)
- **API / framework / dependency migration** → read [references/api-migration.md](references/api-migration.md)

Use the matching spec template in `templates/` when available.

## How It Compares

See [references/comparison.md](references/comparison.md) for detailed comparison with `/goal`, gnhf, and roborev.

| | owloop | /goal | gnhf |
|---|---|---|---|
| Completion check | grep (deterministic) | Haiku model (probabilistic) | grep |
| Context management | Fresh per iteration | Same session | Fresh per iteration |
| Spec format | Constraint-oriented | Free-form prompt | Free-form prompt |

## Links

- **GitHub:** https://github.com/caoergou/owloop
- **Original methodology:** [Geoffrey Huntley's Ralph Wiggum](https://ghuntley.com/ralph/)
- **Forked from:** [fstandhartinger/ralph-wiggum](https://github.com/fstandhartinger/ralph-wiggum)
