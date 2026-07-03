# owloop Roadmap

## Vision

owloop is not just a loop runner — it's a **spec engineering tool**.

The loop itself is trivial (a bash while loop). What's hard — and what owloop solves — is:
1. **Writing specs that converge** instead of looping forever
2. **Verifying completion with evidence** instead of trusting agent self-assessment
3. **Containing blast radius** so a bad overnight run is a `git worktree remove`, not an archaeology project

> "The skill that's becoming scarce: turning taste into checkable constraints."

## Known failure modes (why loop engineering isn't mainstream yet)

These are real, documented problems. owloop must address each one to be worth using.

| Failure mode | Real-world example | owloop's response | Status |
|---|---|---|---|
| **Fix-loop death spiral** | 204 PRs, $900 burned, 12 hours of agent chasing its own tail | Consecutive failure counter (max 3), global iteration cap | ✅ Implemented |
| **Context rot** | Long sessions degrade; agent forgets original goal after compaction | Fresh `claude -p` per iteration, zero accumulated context | ✅ Implemented |
| **Agent self-assessment is unreliable** | Agent reports "PR #51 created" — PR doesn't exist | Completion = grep for `<promise>DONE</promise>`, not agent narrative | ✅ Implemented |
| **"Defined but never called"** | Agent writes function, passes self-review, but function is never wired into call chain | Acceptance Criteria must include integration verification | ⚠️ Spec-dependent |
| **Optimism inflation** | After 100 loops, agent claims "99.8% accuracy" with no measurement | Fresh context prevents accumulation, but spec quality still matters | ⚠️ Spec-dependent |
| **Cost runaway** | Overnight run burns through weekly quota | Token tracking + budget cap | ❌ Not implemented |
| **Review cost underestimated** | 50 commits = 70min of commit-by-commit review | Iteration cap keeps output reviewable | ✅ Implemented |
| **Spec quality is the real bottleneck** | "Build a REST API" → endless loop; vague criteria = vague results | `/owloop-spec` skill with baseline calibration | 🔄 In progress |

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

## v0.2 — Reliable

Focus: **make it not break**, address the failure modes above.

- [ ] Token tracking and budget cap (`--max-tokens`, prevent cost runaway)
- [ ] Subprocess timeout (30min no-output → kill, prevent hung sessions)
- [ ] Semantic fix-loop detection (same files modified 3+ times → stop)
- [ ] Integration verification in spec template ("function exists AND is called")
- [ ] `owloop report` — lavish HTML summary with per-iteration diffs
- [ ] `.claude/` config copying to worktree (permissions survive isolation)
- [ ] PyPI release (`uvx owloop` works without git install)

## v0.3 — Smart Specs

Focus: **the bottleneck is spec quality, not loop mechanics**.

- [ ] `/owloop analyze` — scan codebase, generate problem report (like today's 3-agent analysis)
- [ ] `/owloop-spec` v2 — auto-calibrate acceptance criteria:
  - Run each Acceptance Criteria command BEFORE writing the spec
  - Record baseline values (ruff errors: 84, grep count: 69)
  - Set target based on baseline, not guesswork
- [ ] Spec-from-issue — convert Jira/GitHub issues to specs
- [ ] Spec-from-review — convert code review findings to specs
- [ ] Spec quality score — warn before running: "this spec has no Exclusions" or "Acceptance Criteria uses subjective language"

## v0.4 — Multi-Agent

- [ ] Agent adapter abstraction (ClaudeCodeAdapter, CodexAdapter, OpenCodeAdapter)
- [ ] Parallel spec execution (multiple worktrees, one agent per spec)
- [ ] Independent verifier agent (catch "defined but never called" pattern)
- [ ] Cross-spec dependency tracking

## v1.0 — Production

- [ ] CI/CD pipeline (lint, test, publish on tag)
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
