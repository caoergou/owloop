# CLAUDE.md

Guidance for Claude Code (and other coding agents) working **on the owloop codebase itself**. This is for owloop contributors, not for end users running owloop inside their own projects — those users are served by `README.md` and `skills/owloop/SKILL.md`.

## What owloop is

owloop is a spec-driven autonomous coding loop for Claude Code — "Your code evolves while you sleep." Each iteration spawns a fresh `claude -p` process against one spec, verifies acceptance criteria via shell commands, and commits only on success.

- Repo: https://github.com/caoergou/owloop
- Stack: Python (`click` + `rich`) for the CLI, Bash for the loop engine, PowerShell ports for Windows

## Project structure

| Path | Purpose |
|---|---|
| `src/owloop/cli.py` | Python CLI (`init` / `run` / `plan` / `status` / `version` subcommands), rich console output |
| `pyproject.toml`, `uv.lock` | Packaging (hatchling); `uv` is the dev tool |
| `scripts/owloop.sh` | Core bash loop engine — spawns `claude -p --permission-mode auto` per iteration, sets up worktree isolation, drives the spec queue |
| `scripts/lib/*.sh` | Shared bash helpers. `spec_queue.sh` is used by `owloop.sh`; `circuit_breaker.sh`, `notifications.sh`, `nr_of_tries.sh`, `response_analyzer.sh`, `date_utils.sh` back the legacy `ralph-loop*` scripts |
| `scripts/ralph-loop*.{sh,ps1}` | Upstream-legacy loop variants (Codex / Gemini / Copilot / original Claude) — see "Upstream relationship" |
| `skills/owloop/SKILL.md` | Claude Code skill documenting the constraint-oriented spec methodology |
| `skills/ralph-wiggum/SKILL.md` | Upstream-legacy skill, kept for compatibility |
| `templates/` | Files copied into **consumer** projects by `owloop init` / setup (spec, constitution, checklist, prompts) — not consumed by this repo itself |
| `prototypes/tui_concept.py` | Standalone ANSI TUI concept (owl animation, exit summary) — stdlib only |
| `.claude/commands/` | Slash commands for both `owloop` and legacy `ralph-loop` |

## Dev commands

- `uv run owloop` — smoke-test the CLI (banner + subcommand list)
- `uv run owloop <cmd> --help` — inspect a subcommand
- `bash scripts/owloop.sh -h` — print the bash engine's usage (Chinese output — matches its runtime UX)
- `python prototypes/tui_concept.py` — preview the TUI concept; self-exits after ~20s, or Ctrl+C

There is no test suite yet — verify changes by running the commands above and reading their output.

## Brand

- Primary color: amber `#d4a025` (Rich markup `[bold #d4a025]`, panel/table `border_style`)
- Status icons: 🦉 working · 🌙 iteration done · 💤 stuck/retrying · 🌅 run complete
- Owl ASCII art for banners (`OWLOOP_BANNER` in `cli.py`; `OWL_OPEN` / `OWL_BLINK` / `OWL_SLEEP` frames in the prototype)
- Tone: professional and terse. The existing banner is deliberately small — don't inflate new output with extra colors, borders, or emoji.

## Design principles

- **Auto Mode, not YOLO** — always `--permission-mode auto`, never `--dangerously-skip-permissions`. This is the core premise of the fork; don't regress it.
- **Worktree isolation, zero extra deps** — `owloop.sh` shells out to plain `git worktree add` / `git worktree list`, nothing beyond git itself (no `wt` or other external CLI tool).
- **Constraint-oriented specs** — every spec template carries Requirements, shell-verifiable Acceptance Criteria, Exclusions, Style, and Verification. Exclusions are what keep an unattended loop from wandering; never make that section optional.
- **Fresh context per iteration** — each loop round is a brand-new `claude -p` process. State lives on disk (`specs/`, `logs/`, `IMPLEMENTATION_PLAN.md`), never accumulated in memory across iterations. Don't design features that assume continuity between rounds.

## Upstream relationship

owloop is forked from [fstandhartinger/ralph-wiggum](https://github.com/fstandhartinger/ralph-wiggum), itself built on [Geoffrey Huntley's Ralph Wiggum methodology](https://ghuntley.com/ralph/). Files named `ralph-*` (scripts, skill, slash command) are upstream legacy, kept working for the Codex/Gemini/Copilot variants and backward compatibility. Files named `owloop*` are the rebranded implementation (Auto Mode, worktree isolation, constraint-oriented specs). When fixing a bug, check whether it lives in both trees before assuming `owloop.sh` alone needs the fix. See README's "Differences from Upstream" table for the full diff.
