# Task Routing Guide

When a user asks for help with autonomous/overnight coding, use this guide to decide whether owloop is the right tool, or recommend an alternative.

## Decision Tree

```
Is "done" expressible as a shell command (pass/fail)?
├── NO → Not suitable for owloop
│   ├── Single task, user is present → suggest interactive session
│   └── Subjective/design task → do it manually
│
├── YES → Is it one task or a backlog?
│   ├── ONE task, user is present → suggest `/goal`
│   │   (built-in, no install, same session)
│   │
│   └── BACKLOG (multiple independent tasks) → owloop ✓
│       ├── All tasks are Claude Code? → `owloop run`
│       └── Need multiple agents (Codex, OpenCode)? → suggest gnhf
```

## Quick Reference

| Scenario | Recommended | Why |
|---|---|---|
| Fix 20 lint categories overnight | **owloop** | Backlog of verifiable tasks, unattended |
| Add type annotations to a module | **owloop** | Mechanical, shell-verifiable |
| "Make the API faster" (no metric) | **Not owloop** | No shell-checkable exit condition |
| One bug fix while I watch | **`/goal`** | Single task, user present, built-in |
| Recurring check every 20min | **`/loop`** | Built-in, session-scoped |
| Multi-agent (Claude + Codex) overnight | **gnhf** | Agent-agnostic orchestrator |
| Optimize a metric continuously | **goal-md** | Fitness function approach |
| Design a new feature | **Interactive** | Requires judgment, not automation |

## owloop's Strengths (vs alternatives)

- **Spec queue with priorities** — processes `001-foo.md` before `002-bar.md`
- **Constraint-oriented specs** — explicit Exclusions prevent scope creep
- **Deterministic completion** — `grep` for `<promise>DONE</promise>`, not AI judgment
- **Fix-loop detection** — catches death spirals (same files modified 3+ rounds)
- **Worktree isolation** — main checkout never touched
- **Rich TUI** — full-screen progress with owl animation

## owloop's Limitations

- Claude Code only (no Codex/OpenCode/Copilot adapters yet)
- No cross-iteration memory (each iteration starts fresh — learns nothing from previous failures)
- No token-based cost tracking (only wall-clock `--max-duration`)
