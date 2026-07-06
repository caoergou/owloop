# CLAUDE.md

Guidance for Claude Code (and other coding agents) working **on the owloop codebase itself**. This is for owloop contributors, not for end users running owloop inside their own projects — those users are served by `README.md` and `skills/owloop/SKILL.md`.

## What owloop is

owloop is a spec-driven autonomous coding loop for Claude Code — "Your code evolves while you sleep." Each iteration spawns a fresh `claude -p` process against one spec, verifies acceptance criteria via shell commands, and commits only on success.

- Repo: https://github.com/caoergou/owloop
- Stack: Python (`click` + `rich`) CLI + Python loop engine
- Forked from: [fstandhartinger/ralph-wiggum](https://github.com/fstandhartinger/ralph-wiggum)

## Project structure

| Path | Purpose |
|---|---|
| `src/owloop/cli.py` | Python CLI (`init` / `run` / `plan` / `status` / `version` subcommands), rich console output |
| `src/owloop/engine.py` | Python loop engine — spawns agent per iteration, manages worktree, drives spec queue |
| `src/owloop/adapters.py` | Agent adapter abstraction (`ClaudeCodeAdapter`, `MockAdapter`) |
| `src/owloop/tui.py` | Full-screen Rich TUI with owl animation |
| `src/owloop/reporter.py` | Plain-text event reporter for non-interactive terminals |
| `src/owloop/spec_queue.py` | Spec discovery, status, priority helpers |
| `pyproject.toml`, `uv.lock` | Packaging (hatchling); `uv` is the dev tool |
| `skills/owloop/SKILL.md` | Core loop engineering methodology skill (agent-agnostic) |
| `skills/owloop-spec/SKILL.md` | Interactive spec-creation wizard skill |
| `skills/owloop-loop-control/SKILL.md` | Promise protocol and loop convergence skill |
| `skills/owloop-verify/SKILL.md` | Verification pipeline and baseline calibration skill |
| `skills/owloop/references/` | Scenario references for the core skill |
| `.claude/commands/` | Slash commands for owloop |
| `templates/` | Files copied into **consumer** projects by `owloop init` (spec, constitution, checklist, prompts) |
| `prototypes/tui_concept.py` | Standalone ANSI TUI concept (owl animation, exit summary) — stdlib only |
| `.claude/commands/` | Slash commands for owloop |
| `tests/` | pytest test suite |

## Dev commands

- `uv run owloop` — smoke-test the CLI (banner + subcommand list)
- `uv run owloop <cmd> --help` — inspect a subcommand
- `uv run pytest -q` — run the test suite with coverage
- `uv run ruff check src/owloop tests` — lint and import sorting
- `uv run mypy src/owloop tests` — static type checking
- `python prototypes/tui_concept.py` — preview the TUI concept; self-exits after ~20s, or Ctrl+C

## Brand

- Mascot: **Ollie** the owl — the overnight pair programmer who watches your repo while you sleep.
- Primary color: amber `#d4a025` (Rich markup `[bold #d4a025]`, panel/table `border_style`)
- Status icons: 🦉 working · 🌙 iteration done · 💤 stuck/retrying · 🌅 run complete
- Brand assets live in `src/owloop/_brand.py`: palette, owl ASCII art (`OWL_SMALL` / `OWL_MEDIUM` / `OWL_BLINK` / `OWL_SLEEP`), moon phases, spinner frames, and state-aware messages.
- ASCII fallbacks and `--no-color` mode must remain functional; don't rely on emoji or Unicode block characters for critical information.
- Tone: professional and terse. The banner is deliberately small — don't inflate new output with extra colors, borders, or emoji.

## Design principles

- **Auto Mode, not YOLO** — always `--permission-mode auto`, never `--dangerously-skip-permissions`. This is the core premise of the fork; don't regress it.
- **Worktree isolation, zero extra deps** — the engine uses plain `git worktree add` / `git worktree list`, nothing beyond git itself.
- **Constraint-oriented specs** — every spec template carries Requirements, shell-verifiable Acceptance Criteria, Exclusions, Style, and Verification. Exclusions are what keep an unattended loop from wandering; never make that section optional.
- **Fresh context per iteration** — each loop round is a brand-new `claude -p` process. State lives on disk (`.owloop/specs/`, `.owloop/logs/`), never accumulated in memory across iterations. Don't design features that assume continuity between rounds.
