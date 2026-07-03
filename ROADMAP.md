# owloop Roadmap

## Vision

owloop is not just a loop runner — it's a **spec engineering tool**.

The loop itself is trivial (a bash while loop). What's hard — and what owloop solves — is:
1. **Writing specs that converge** instead of looping forever
2. **Verifying completion with evidence** instead of trusting agent self-assessment
3. **Containing blast radius** so a bad overnight run is a `git worktree remove`, not an archaeology project

> "The skill that's becoming scarce: turning taste into checkable constraints."

## What we learned from the ecosystem

We audited `gnhf`, `ralphloop.sh`, `goal-md`, `/goal`, `/loop`, `roborev`, and `spec-kit`. Four things became clear:

### 1. Pre-flight spec validation is a blue ocean
No existing tool validates spec quality before the loop starts. `spec-kit` (117k+ stars) exposes a quality check, but it is opt-in; the community is asking for it to be mandatory. owloop can be the first loop runner that refuses to start a bad spec.

### 2. Fresh context is a double-edged sword
`gnhf` keeps cross-iteration memory via `notes.md` (auto-appended summary + key learnings, read by the next iteration). `/goal` keeps state in a single session. owloop chose fresh `claude -p` per iteration to avoid context rot, but that also means the agent repeats mistakes. v0.3 closes this gap with `run-notes.md` without sacrificing isolation.

### 3. Deterministic completion beats model judgment
`/goal` uses a Haiku model to decide when a task is done; this is probabilistic and can mis-fire. `gnhf` trusts the agent to self-report. owloop uses a hard `grep` for `<promise>DONE</promise>`. We are extending this in v0.4 to support `<promise>BLOCKED:reason</promise>` and `<promise>DECIDE:question</promise>` (borrowed from `ralphloop.sh`) so the loop can distinguish "done", "stuck", and "needs human decision".

### 4. Borrowings that are cheap and high-value
| Source | Design | How owloop adopts it |
|---|---|---|
| `ralphloop.sh` | `STEERING.md` — edit mid-flight, agent reads every iteration | v0.3: add `STEERING.md` support |
| `ralphloop.sh` | Promise exit codes (COMPLETE / BLOCKED / DECIDE) | v0.4: extend promise protocol |
| `gnhf` | `notes.md` cross-iteration memory | v0.3: `run-notes.md` |
| `gnhf` | Prevent system sleep (`caffeinate`, `systemd-inhibit`) | v0.3: cross-platform sleep inhibitor |
| `gnhf` | Rich exit report with diff stats and token usage | v0.3: `owloop report` summary |
| `gnhf` | Exponential backoff on hard errors | v0.3: replace fixed "3 failures = reset" |

### 5. Things we intentionally will not do
- **Docker sandbox isolation** (`ralphloop` style): too heavy. Git worktree isolation is enough for blast-radius containment.
- **Fitness-function optimization** (`goal-md` style): a different paradigm. owloop is for discrete pass/fail tasks; continuous metric optimization belongs in a different tool class.
- **Multi-agent adapters in the near term**: `gnhf` demonstrates that agent-agnostic orchestration introduces a lot of JSON parsing / protocol fragility. We will keep Claude Code as the first-class adapter until the spec format is rock solid.

## Known failure modes (why loop engineering isn't mainstream yet)

These are real, documented problems. owloop must address each one to be worth using.

| Failure mode | Real-world example | owloop's response | Status |
|---|---|---|---|
| **Fix-loop death spiral** | 204 PRs, $900 burned, 12 hours of agent chasing its own tail | Consecutive failure counter (max 3), global iteration cap | ✅ Implemented |
| **Context rot** | Long sessions degrade; agent forgets original goal after compaction | Fresh `claude -p` per iteration, zero accumulated context | ✅ Implemented |
| **Agent self-assessment is unreliable** | Agent reports "PR #51 created" — PR doesn't exist | Completion = grep for `<promise>DONE</promise>`, not agent narrative | ✅ Implemented |
| **"Defined but never called"** | Agent writes function, passes self-review, but function is never wired into call chain | Acceptance Criteria must include integration verification | ⚠️ Spec-dependent |
| **Optimism inflation** | After 100 loops, agent claims "99.8% accuracy" with no measurement | Fresh context prevents accumulation, but spec quality still matters | ⚠️ Spec-dependent |
| **Cost runaway** | Overnight run burns through weekly quota | Token tracking + budget cap | ✅ Implemented |
| **Review cost underestimated** | 50 commits = 70min of commit-by-commit review | Iteration cap keeps output reviewable | ✅ Implemented |
| **Spec quality is the real bottleneck** | "Build a REST API" → endless loop; vague criteria = vague results | `/owloop-spec` skill with baseline calibration | ✅ Implemented |

### Geoffrey Huntley's own warning

> "If you just set it off and run away, you're not going to get a great outcome. You really want to babysit this thing."

owloop's response: don't pretend babysitting isn't needed. Instead, **make babysitting efficient** — structured specs, capped iterations, commit-by-commit history, lavish report in the morning.

## v0.1 (current)

- [x] Bash loop engine (fork from ralph-wiggum)
- [x] Python engine (replaces bash, zero external script dependency)
- [x] Rich TUI with owl animation
- [x] Auto Mode (replaces YOLO)
- [x] Git worktree isolation
- [x] Constraint-oriented spec format
- [x] Python CLI (init/run/plan/status/version)
- [x] Preflight checks (claude availability, clean worktree, spec validation)
- [x] ANSI stripping for completion signal detection
- [x] Consecutive failure detection (max 3)
- [x] Social preview + GitHub topics + GEO-optimized README
- [x] Basic test suite (14 tests)

## v0.2 — Reliable (current)

Focus: **make it not break**, address the failure modes above.

- [x] Subprocess idle timeout (`--idle-timeout`, default 60min, prevent hung sessions)
- [x] Semantic fix-loop detection (same files modified 3+ consecutive iterations → warning)
- [x] Duration cap (`--max-duration`, prevent cost runaway via wall-clock limit)
- [x] `.claude/` config copying to worktree (permissions survive isolation)
- [x] Legacy bash engine removed (Python engine is the sole engine)
- [x] Skills bilingual rewrite (Chinese + English trigger support)
- [x] Skills restructured per agentskills.io spec (references/ directory)
- [x] Token tracking and budget cap (`--max-tokens`, per-iteration token counting)
- [x] `owloop report` — HTML summary with per-iteration diff stats and token usage
- [x] PyPI release workflow (`uvx owloop` installable on tag)

## v0.3 — Memory & Cost Control

Focus: **close the two biggest gaps vs gnhf** — cross-iteration learning and token-based cost control. Also adopt the cheap, high-value ergonomics from `ralphloop.sh` and `gnhf`.

- [x] Cross-iteration notes (`run-notes.md`): auto-append summary + learnings after each iteration; next iteration reads it. Solves "fresh context = repeated mistakes"
- [x] `--max-tokens`: parse token counts from claude output, abort when cumulative limit reached
- [x] Rich exit summary: diff stats (files changed, lines added/deleted), token usage, branch diff, review commands
- [x] Prevent system sleep during run (`caffeinate` on macOS, `systemd-inhibit` on Linux, `SetThreadExecutionState` on Windows)
- [x] Exponential backoff on hard errors (replace current "3 failures = warning + reset")
- [x] `STEERING.md`: agent reads this file each iteration for mid-flight course corrections (inspired by ralphloop.sh)

## v0.4 — Smart Specs

Focus: **the bottleneck is spec quality, not loop mechanics**. Pre-flight spec validation is a blue ocean — `spec-kit` only offers it opt-in, and the community is asking for it to be mandatory. owloop can be the first loop runner that refuses to start a bad spec.

- [ ] Spec pre-flight linter (`owloop check`): run before loop starts
  - Verify all acceptance criteria are executable shell commands
  - Check Exclusions section is non-empty
  - Detect internal contradictions
  - Run baseline commands and confirm they execute without error
- [ ] Community spec template library (legacy refactor, ML hygiene, API migration, etc.)
- [ ] Spec-from-issue — convert Jira/GitHub issues to specs
- [ ] Spec-from-review — convert code review findings to specs
- [ ] Promise protocol: support `<promise>BLOCKED:reason</promise>` and `<promise>DECIDE:question</promise>` in addition to `DONE` (inspired by ralphloop.sh)

## v0.5 — Multi-Agent

Intentionally later: `gnhf` shows that agent-agnostic orchestration adds significant protocol fragility (JSON parsing, tool schema mismatches). We will keep Claude Code first-class until the spec format and verification pipeline are rock solid.

- [ ] Additional agent adapters (CodexAdapter, OpenCodeAdapter)
- [ ] Parallel spec execution (multiple worktrees, one agent per spec)
- [ ] Independent verifier agent (catch "defined but never called" pattern)
- [ ] Cross-spec dependency tracking

## v1.0 — Production

- [x] CI/CD pipeline (lint, test, publish on tag)
- [ ] Comprehensive docs site
- [ ] skills.sh registration (need to contact vercel-labs for indexing)
- [ ] Community spec library (reusable spec templates for common refactoring patterns)
- [ ] Cost analytics dashboard (token spend per spec, per iteration)

---

## What tasks work well with owloop

### Best fit (mechanical, verifiable, boring)
- Lint/type error fixes
- Dead code removal
- Extract repeated patterns (DRY)
- Add type annotations
- Generate characterization tests
- Dependency version updates
- Import cleanup and organization
- Code formatting standardization

### Good fit (structured, bounded)
- Service layer extraction (with blueprint)
- Schema migration (Marshmallow → Pydantic)
- API documentation generation
- Log/print standardization
- Error handling unification
- Model mixin extraction

### Poor fit (requires judgment)
- Feature design decisions
- Architecture changes without blueprint
- Performance optimization without clear metrics
- Security-sensitive code changes
- UI/UX decisions
- Database schema design

### Rule of thumb
If you can write a shell command that verifies "done", it's a good owloop task.
If "done" requires a human to look at it and decide, it's not.

---

## Core insight

> Loop engineering isn't about making the agent smarter. It's about making failure cheap, inspectable, and bounded — then letting the agent brute-force convergence against constraints you defined.

The agent WILL fail. The question is whether failure costs you $5 and a `git worktree remove`, or $900 and a weekend of cleanup.
