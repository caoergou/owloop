---
name: owloop
description: Autonomous AI coding with constraint-oriented, spec-driven development. Implements Geoffrey Huntley's iterative bash loop methodology where agents work through specs one at a time, outputting a completion signal only when acceptance criteria are 100% met.
license: MIT
metadata:
  author: caoergou
  version: "1.0"
  repository: https://github.com/caoergou/owloop
---

# Owloop

> Autonomous AI coding with constraint-oriented, spec-driven development

## What is Owloop?

Owloop combines **Geoffrey Huntley's iterative bash loop** with **spec-driven development** for fully autonomous AI-assisted software development.

The key insight: **Fresh context each iteration**. Each loop starts a new agent process with a clean context window, preventing context overflow and degradation.

## When to Use This Skill

Use Owloop when:

- You have multiple specifications/features to implement
- You want the AI to work autonomously through tasks
- You need consistent, verifiable completion of acceptance criteria
- You want to avoid context window problems in long sessions

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                     OWLOOP LOOP                              │
├─────────────────────────────────────────────────────────────┤
│  Loop 1: Pick spec A → Implement → Test → Commit → DONE    │
│  Loop 2: Pick spec B → Implement → Test → Commit → DONE    │
│  Loop 3: Pick spec C → Implement → Test → Commit → DONE    │
│  ...                                                        │
│                                                             │
│  Each iteration = Fresh context window                      │
│  Shared state = Files on disk (specs, plan, history)        │
└─────────────────────────────────────────────────────────────┘
```

## Installation

### Quick Install (via Skill Installers)

```bash
# Using Vercel's add-skill
npx add-skill caoergou/owloop

# Using OpenSkills
openskills install caoergou/owloop
```

### Full Setup (Recommended)

For full Owloop setup with constitution and interview:

```bash
# Tell your AI agent:
"Set up Owloop using https://github.com/caoergou/owloop"
```

The agent will guide you through a **lightweight, pleasant setup**:

1. **Quick Setup** (~1 min) — Create directories, download scripts
2. **Project Interview** — Focus on your **vision and goals** (not tech details)
3. **Constitution** — Create a guiding document for all sessions
4. **Next Steps** — Clear guidance on creating specs and starting Owloop

For existing projects, the agent detects your tech stack automatically. The interview prioritizes understanding *what you're building and why*.

## Core Concepts

### 1. Fresh Context Each Loop

Each iteration of the Owloop loop starts a new AI agent process. This means:
- No context window overflow
- No degradation over time
- Clean slate for each task

### 2. Shared State on Disk

State persists between loops via files:
- `specs/` — Feature specifications with acceptance criteria
- `owloop_history.txt` — Log of breakthroughs, blockers, learnings
- `IMPLEMENTATION_PLAN.md` — Optional detailed task breakdown

### 3. Completion Signal

The agent outputs `<promise>DONE</promise>` **ONLY** when:
- All acceptance criteria are verified
- Tests pass
- Changes are committed and pushed

The bash loop checks for this phrase. If not found, it retries.

### 4. Backpressure via Tests

Tests, lints, and builds act as guardrails. The agent must fix issues before outputting the completion signal.

### 5. Constraint-Oriented Specs

Beyond Requirements and Acceptance Criteria, Owloop specs carry three constraint sections that keep an unattended run from wandering (see `templates/spec-template.md`):

- **Exclusions** — What NOT to touch: files/modules out of scope, behaviors that must not change. This is the highest-leverage section for preventing scope creep during autonomous runs.
- **Style** — Conventions to follow (naming, existing patterns, libraries already in use) so generated code matches the codebase instead of introducing a new one-off style.
- **Verification** — The exact commands to run after each change. Owloop runs these itself before it's allowed to output the completion signal — vague verification steps produce vague confidence.

## Usage

### Creating Specifications

**The key to success:** Each spec needs **clear, testable acceptance criteria** and explicit boundaries. This is what tells Owloop when a task is truly "done" — and what it should leave alone.

```markdown
# Feature: User Authentication

## Priority: 1

## Requirements
- OAuth login with Google
- Session management
- Logout functionality

## Acceptance Criteria
- [ ] User can log in with Google
- [ ] Session persists across page reloads
- [ ] User can log out
- [ ] Tests pass

## Exclusions
- Do not touch the existing `LegacyAuth` module
- Do not change the database schema

## Style
- Follow the existing `services/*Service.ts` pattern

## Verification
- `npm test -- auth`
- `npm run lint`

Output when complete: `<promise>DONE</promise>`
```

**Good criteria:** "User can log in with Google and session persists"
**Bad criteria:** "Auth works correctly"

The more specific your acceptance criteria — and the more explicit your exclusions — the better Owloop performs.

### Running the Loop

```bash
# Start building (Claude Code)
./scripts/owloop-loop.sh

# With max iterations
./scripts/owloop-loop.sh 20

# Using Codex CLI
./scripts/owloop-loop-codex.sh
```

### Logging (All Output Captured)

Every loop run writes **all output** to log files in `logs/`:

- **Session log:** `logs/owloop_*_session_YYYYMMDD_HHMMSS.log` (entire run, including CLI output)
- **Iteration logs:** `logs/owloop_*_iter_N_YYYYMMDD_HHMMSS.log` (per-iteration CLI output)
- **Codex last message:** `logs/owloop_codex_output_iter_N_*.txt`

## Two Modes

| Mode | Purpose | Command |
|------|---------|---------|
| **build** (default) | Pick spec, implement, test, commit | `./scripts/owloop-loop.sh` |
| **plan** (optional) | Create detailed task breakdown | `./scripts/owloop-loop.sh plan` |

## Key Principles

### Let Owloop Loop

Trust the AI to self-identify, self-correct, and self-improve. Observe patterns and adjust prompts.

### Auto Mode (Not YOLO)

Owloop still needs full autonomy to run end-to-end without stopping for approval on every edit or command — but that trade-off deserves a deliberate name, not a meme:

- Claude Code: `--dangerously-skip-permissions`
- Codex: `--dangerously-bypass-approvals-and-sandbox`

This is **auto mode**: standing approval to keep moving, not a license to skip review. Pair it with worktree isolation below.

### Worktree Isolation

Run each Owloop loop in its own `git worktree`, on a dedicated branch, instead of your primary working copy:

```bash
git worktree add ../myproject-owloop-spec-001 -b owloop/spec-001
cd ../myproject-owloop-spec-001
./scripts/owloop-loop.sh
```

Autonomous edits, commits, and test runs stay contained to that worktree. Review the diff and merge — or just delete the worktree — once the loop outputs `<promise>DONE</promise>`. If a loop goes off the rails, the blast radius is a disposable worktree, not your main branch.

⚠️ **Still review before merging.** Auto mode plus worktree isolation reduces risk; it does not replace review.

## Links

- **GitHub:** https://github.com/caoergou/owloop
- **Original methodology:** [Geoffrey Huntley's how-to-ralph-wiggum](https://github.com/ghuntley/how-to-ralph-wiggum)
- **Forked from:** [fstandhartinger/ralph-wiggum](https://github.com/fstandhartinger/ralph-wiggum)
