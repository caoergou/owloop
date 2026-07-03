<div align="center">

<img src=".github/social-preview.png" alt="owloop — Your code evolves while you sleep" width="720">

<br>

[![PyPI](https://img.shields.io/pypi/v/owloop?color=d4a025)](https://pypi.org/project/owloop/)
[![MIT License](https://img.shields.io/badge/license-MIT-d4a025)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-d4a025)](https://python.org)
[![CI](https://github.com/caoergou/owloop/actions/workflows/ci.yml/badge.svg)](https://github.com/caoergou/owloop/actions/workflows/ci.yml)
[![Agent Skill](https://img.shields.io/badge/agent--skill-owloop-d4a025)](https://agentskills.io)
[![Website](https://img.shields.io/badge/website-eric.run.place%2Fowloop-d4a025)](https://eric.run.place/owloop/)

*Your code evolves while you sleep.*

**Write specs. Start the loop. Wake up to clean commits.**

> 🦉 Ollie is a nocturnal owl.
>
> While you sleep, he reads your specs, spawns a fresh agent iteration for each task,
> verifies the result with real shell commands, and only commits when they pass.

[Quick Start](#-quick-start) · [How It Works](#-how-it-works) · [Writing Specs](#-writing-specs) · [Compared To](#-compared-to) · [FAQ](#-faq)

</div>

---

> You have 20 lint categories to fix, 200 functions missing type annotations, and error handling copy-pasted everywhere. You know what to do — you just don't have the hours. **owloop does it while you sleep.**

```
owloop run → pick spec → fresh agent context → verify with shell commands → commit → next spec → 🌅
```

## 🌙 Quick Start

```bash
# Install from PyPI
uv tool install owloop
# or: pip install owloop

owloop init        # creates .owloop/ only
owloop spec "refactor error handling"   # cc scans code, drafts spec, asks for approval
# edit .owloop/specs/01-example.md if needed, then:
owloop run         # start the loop
```

<details>
<summary><strong>All commands</strong></summary>

| Command | Description |
|---|---|
| `owloop init` | Initialize project (creates `.owloop/`, `.gitignore` entries) |
| `owloop spec "goal"` | Turn a vague goal into a concrete spec via agent clarification and approval |
| `owloop check` | Validate all specs before running the loop (pre-flight linter) |
| `owloop run` | Start the autonomous loop with TUI |
| `owloop run -n 20` | Limit to 20 iterations |
| `owloop run --max-duration 120` | Stop after 2 hours |
| `owloop run --max-tokens 200000` | Stop after token budget reached |
| `owloop run --idle-timeout 1800` | Kill hung agent after 30min silence |
| `owloop status` | Show specs and completion progress |
| `owloop report` | Generate AI-powered HTML summary report (default) |
| `owloop report --no-ai` | Generate fast, offline HTML summary report |
| `owloop report --open` | Generate AI report and open with lavish-axi |
| `owloop spec-from-issue 42` | Generate a spec draft from a GitHub issue |
| `owloop version` | Show installed version |

**Global options**

| Option | Description |
|---|---|
| `--ascii` | Use ASCII art instead of Unicode glyphs (better on older Windows terminals) |
| `--no-color` | Disable colored terminal output |
| `--compact` | Force the compact single-column TUI layout |

</details>

## 🦉 How It Works

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#d4a025', 'primaryTextColor': '#0b1026', 'primaryBorderColor': '#3a4270', 'lineColor': '#3a4270', 'secondaryColor': '#121a2e', 'tertiaryColor': '#121a2e', 'fontFamily': 'Inter, system-ui, sans-serif' }}}%%
graph LR
    A["🦉 Pick spec"]:::owl --> B["fresh agent context"]:::neutral
    B --> C{"DONE?"}:::neutral
    C -- yes --> D["✅ Commit"]:::neutral --> E{"More specs?"}:::neutral
    C -- no --> R["🔄 Retry ≤3"]:::retry --> A
    E -- yes --> A
    E -- no --> F["🌅 Complete"]:::done

    classDef owl fill:#d4a025,stroke:#d4a025,color:#0b1026
    classDef done fill:#8fd19e33,stroke:#8fd19e,color:#f2ecd8
    classDef retry fill:#e0777d33,stroke:#e0777d,color:#f2ecd8
    classDef neutral fill:#121a2e,stroke:#3a4270,color:#f2ecd8
```

| Property | How |
|---|---|
| **Natural-language specs** | `owloop spec "goal"` scans the codebase, calibrates baselines, drafts a complete spec, and waits for approval. |
| **Pre-flight linting** | `owloop check` validates specs before the loop starts — no wasted tokens on bad specs. |
| **Fresh context** | Each iteration starts a brand-new agent process. No context rot. |
| **Cross-iteration notes** | `run-notes.md` carries learnings between iterations — fresh context without repeating mistakes. |
| **Deterministic completion** | `grep` for `<promise>DONE</promise>` — no AI judgment, no surprises. |
| **Worktree isolation** | Runs in a separate `git worktree`. Your main checkout stays untouched. |
| **AI-generated reports** | `owloop report` analyzes the run with Claude and produces a reviewable HTML artifact. |
| **Auto Mode** | `--permission-mode auto`: Ollie asks before risky moves, never YOLO. |
| **Fix-loop detection** | Same files modified 3+ rounds → Ollie warns of a death spiral. |
| **Token budget cap** | `--max-tokens` stops the run before costs spiral. |
| **Sleep prevention** | Keeps your machine awake during overnight runs (macOS / Linux / Windows). |

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

## Style
- Follow existing Flask error handler pattern in backend/app/__init__.py

## Stuck Behavior
- If you cannot make progress after 2 attempts at the same error, add a
  `## Blockers` section to this spec, commit partial work, and output
  `<promise>DONE</promise>`.

## Verification
After each change: uv run ruff check backend/

## Baseline
- `grep -c "except ValidationError" backend/app/api/*.py`: 69 at start, target ≤ 5
- `uv run ruff check backend/`: 0 errors at start, target 0

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

## 🛠️ Development

owloop uses `uv` for dependency management and ships with `ruff`, `mypy`, and `pytest-cov` as dev tools.

```bash
uv sync --group dev          # install dev dependencies
uv run pytest -q             # run tests with coverage
uv run ruff check src/owloop tests
uv run mypy src/owloop tests
```

All changes are validated on Linux, macOS, and Windows via GitHub Actions.

## 🦉 Brand

<p align="center">
  <img src=".github/owl.svg" alt="Ollie the owl" width="160">
</p>

owloop's identity — Ollie the owl, the night/amber palette, and the "your code evolves while you sleep" story — is documented in [.github/BRAND.md](.github/BRAND.md).

## Credits

Built on [Geoffrey Huntley's Ralph Wiggum methodology](https://ghuntley.com/ralph/), forked from [Florian Standhartinger's implementation](https://github.com/fstandhartinger/ralph-wiggum).

## License

[MIT](LICENSE)
