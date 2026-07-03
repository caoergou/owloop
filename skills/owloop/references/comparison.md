# Owloop vs Other Loop Tools

## Detailed Comparison

| Feature | owloop | /goal | gnhf | roborev |
|---|---|---|---|---|
| **Completion check** | grep `<promise>DONE</promise>` (deterministic) | Haiku model judgment (probabilistic) | grep | AI review |
| **Context management** | Fresh `claude -p` per iteration | Same session accumulates | Fresh per iteration | Fresh per iteration |
| **Spec format** | Constraint-oriented (Exclusions + shell criteria) | Free-form prompt | Free-form prompt | Review guidelines |
| **Install footprint** | Zero (`uvx`) | Built-in to Claude Code | `npm -g` | `brew`/`go install` |
| **Worktree isolation** | Built-in (default on) | No | No | N/A |
| **Permission model** | `--permission-mode auto` | Interactive | YOLO / configurable | N/A |
| **Stuck detection** | 3 consecutive failures | Model decides | Configurable | N/A |
| **Fix-loop detection** | Same files modified 3+ rounds | None | None | N/A |
| **Duration cap** | `--max-duration` flag | None | None | N/A |
| **TUI** | Full-screen Rich TUI with owl animation | None | Terminal output | None |
| **Multi-agent** | Claude Code only (adapters planned) | Claude Code only | Agent-agnostic | Agent-agnostic |

## When to Use Which

### Use owloop when:
- You have a **backlog** of well-defined tasks (not just one)
- Each task can be independently verified with shell commands
- You want to run **unattended for hours** (overnight, weekend)
- You need **worktree isolation** (main checkout stays clean)
- You want **deterministic completion** (grep, not AI judgment)

### Use `/goal` when:
- You have **one focused task** in the current sitting
- You're present to monitor and redirect
- The task is interactive or exploratory
- You don't want to install anything extra

### Use gnhf when:
- You need **multi-agent support** (Codex, Gemini, Copilot, OpenCode)
- You want shared `notes.md` memory across iterations
- You prefer agent-agnostic tooling

### Use roborev when:
- You want **continuous review** of every commit (complementary to any loop tool)
- You're catching issues in agent-written commits after the fact

## Upstream Differences

owloop is forked from [fstandhartinger/ralph-wiggum](https://github.com/fstandhartinger/ralph-wiggum):

| | ralph-wiggum (upstream) | owloop |
|---|---|---|
| Permission model | `--dangerously-skip-permissions` (YOLO) | `--permission-mode auto` |
| Repo safety | Runs on your checkout directly | Worktree isolation (default) |
| Spec format | Requirements + manual checklists | Constraint-oriented (Exclusions + shell-verifiable criteria) |
| Engine | Bash only | Python (click + rich) with TUI |
| Run report | Terminal + logs | TUI + plain reporter |
