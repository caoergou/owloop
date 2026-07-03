<div align="center">

<img src=".github/social-preview.png" alt="owloop — Your code evolves while you sleep" width="720">

<br>

[![MIT License](https://img.shields.io/badge/license-MIT-d4a025)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-d4a025)](https://python.org)
[![Agent Skill](https://img.shields.io/badge/agent--skill-owloop-d4a025)](https://agentskills.io)

**Spec-driven autonomous coding loop for Claude Code.**<br>
Fresh context · Shell-verified completion · Worktree isolation

[Quick Start](#-quick-start) · [How It Works](#-how-it-works) · [Writing Specs](#-writing-specs) · [Compared To](#-compared-to) · [FAQ](#-faq)

</div>

---

Turn your backlog of lint warnings, missing type annotations, and copy-pasted error handling into constraint-oriented specs. Run `owloop run`. Go to sleep. Each iteration spawns a fresh `claude -p`, verifies acceptance criteria with real shell commands, and commits only when they pass.

## 🚀 Quick Start

```bash
uv tool install git+https://github.com/caoergou/owloop

owloop init        # creates specs/ and templates
# edit specs/01-example.md with your task
owloop run         # start the loop
```

<details>
<summary><strong>All commands</strong></summary>

| Command | Description |
|---|---|
| `owloop init` | Initialize project (creates `specs/`, `.gitignore` entries) |
| `owloop run` | Start the autonomous loop with TUI |
| `owloop run -n 20` | Limit to 20 iterations |
| `owloop run --max-duration 120` | Stop after 2 hours |
| `owloop run --idle-timeout 1800` | Kill hung agent after 30min silence |
| `owloop plan` | Generate implementation plan from specs |
| `owloop status` | Show specs and completion progress |

</details>

## ⚙️ How It Works

```mermaid
graph LR
    A["🦉 Pick spec"] --> B["claude -p<br/>fresh context"]
    B --> C{"DONE?"}
    C -- yes --> D["✅ Commit"] --> E{"More specs?"}
    C -- no --> R["🔄 Retry ≤3"] --> A
    E -- yes --> A
    E -- no --> F["🌅 Complete"]

    style A fill:#d4a025,color:#0b1026,stroke:#d4a025
    style F fill:#22c55e20,stroke:#22c55e
    style R fill:#ef444420,stroke:#ef4444
```

| Property | How |
|---|---|
| **Fresh context** | Each iteration = new `claude -p` process. No context rot. |
| **Deterministic completion** | `grep` for `<promise>DONE</promise>`, not AI judgment. |
| **Worktree isolation** | Runs in a separate `git worktree`. Main checkout untouched. |
| **Auto Mode** | `--permission-mode auto`, never YOLO. |
| **Stuck detection** | 3 consecutive failures → warning + reset. |
| **Fix-loop detection** | Same files modified 3+ rounds → warns of death spiral. |
| **Duration cap** | `--max-duration` prevents overnight cost runaway. |

## 📝 Writing Specs

Specs are **constraint-oriented**: define what's off-limits, then make every acceptance criterion a shell command.

```markdown
# Spec: Extract ValidationError Handling

## Priority: 1

## Requirements
- Extract ~69 repeated `except ValidationError` blocks into
  a single Flask `@app.errorhandler(ValidationError)`

## Acceptance Criteria
- [ ] grep -c "except ValidationError" backend/app/api/*.py  →  ≤ 5
- [ ] uv run ruff check backend/  →  0 errors
- [ ] grep -c "errorhandler" backend/app/__init__.py  →  ≥ 1

## Exclusions
- Do NOT change API response formats
- Do NOT touch models/, schemas/, services/

## Verification
After each change: uv run ruff check backend/

Output when complete: `<promise>DONE</promise>`
```

> **Why this works:** `Exclusions` prevent drift. Shell commands verify "done" — no AI judgment needed. One spec = one concern.

<details>
<summary><strong>Rule of thumb</strong></summary>

If you can write a shell command that verifies "done", it's a good owloop task. If "done" requires a human to look and decide, it's not.

**Best fit:** lint fixes, type annotations, dead code removal, DRY extraction, import cleanup<br>
**Poor fit:** feature design, architecture decisions, UI/UX, security-sensitive changes

</details>

## 🔄 Compared To

| | owloop | `/goal` | [gnhf](https://github.com/kunchenguid/gnhf) |
|---|---|---|---|
| **Completion** | grep (deterministic) | Haiku model (probabilistic) | grep |
| **Context** | Fresh per iteration | Same session | Fresh per iteration |
| **Specs** | Constraint-oriented | Free-form | Free-form |
| **Best for** | Backlog of verifiable tasks | One focused task | Multi-agent overnight |

## ❓ FAQ

<details>
<summary><strong>When should I use owloop instead of <code>/goal</code>?</strong></summary>

`/goal` is great for one task in one sitting. owloop is for backlogs — a queue of specs, each run in a fresh context, unattended overnight. If you're clearing twenty lint categories or migrating a whole module, loop engineering scales further than one long session.

</details>

<details>
<summary><strong>Is this safe to run on production code?</strong></summary>

owloop runs in a separate `git worktree` with `--permission-mode auto`. Your main branch stays clean. That said, treat every overnight run as a PR to review in the morning, not a deploy.

</details>

<details>
<summary><strong>Can I use owloop with Codex or OpenCode?</strong></summary>

Not directly — owloop is built around `claude -p`. For multi-agent support, [gnhf](https://github.com/kunchenguid/gnhf) is the better fit.

</details>

## Credits

Built on [Geoffrey Huntley's Ralph Wiggum methodology](https://ghuntley.com/ralph/), forked from [Florian Standhartinger's implementation](https://github.com/fstandhartinger/ralph-wiggum).

## License

[MIT](LICENSE)
