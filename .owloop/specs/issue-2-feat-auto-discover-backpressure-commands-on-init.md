# Feature: feat: auto-discover backpressure commands on init

## Priority: 3

## Requirements
## Problem

Backpressure (tests, lint, type check, build) is the foundation of loop reliability. Without it, the agent grades its own homework.

Currently owloop relies on the user (or the spec-generation agent) to manually specify acceptance criteria commands. But every project already has these commands defined in `pyproject.toml`, `package.json`, `Makefile`, `Cargo.toml`, etc.

## Proposal

During `owloop init` or `owloop go`, auto-scan the project for verification commands:

| Source | Commands |
|---|---|
| `pyproject.toml` [tool.pytest] | `pytest tests/` |
| `pyproject.toml` [tool.ruff] | `ruff check src/` |
| `pyproject.toml` [tool.mypy] | `mypy src/` |
| `package.json` scripts.test | `npm test` |
| `package.json` scripts.lint | `npm run lint` |
| `Makefile` test/lint targets | `make test`, `make lint` |
| `Cargo.toml` | `cargo test`, `cargo clippy` |
| `.github/workflows/*.yml` | extract run commands |

Store discovered commands in `.owloop/backpressure.json`. The spec generator and build prompt can reference these automatically, so every spec gets project-appropriate verification without manual configuration.

## Why this matters

> "Create backpressure via tests, typechecks, lints, builds — that will reject invalid/unacceptable work." — [Ralph Playbook](https://github.com/moule3053/ralph-playbook)

> "if you didn't test it, it doesn't work" — [ralphloop.sh](https://ralphloop.sh/blog/what-is-the-ralph-technique/)

## Effort estimate

Small — mostly `grep`/`json.loads` on known config files. No agent calls needed.

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
