# owloop Roadmap

## Vision

owloop is not just a loop runner — it's an **autonomous code improvement pipeline**:
Discover problems → Generate specs → Execute with verification → Report results.

## v0.1 (current)

- [x] Bash loop engine (fork from ralph-wiggum)
- [x] Auto Mode (replaces YOLO)
- [x] Git worktree isolation
- [x] Constraint-oriented spec format
- [x] Python CLI (init/run/plan/status/version)
- [x] Social preview + GitHub topics
- [ ] Python engine (replacing bash) — in progress
- [ ] Rich TUI with owl animation — in progress
- [ ] Agent adapter abstraction — in progress

## v0.2 — Usable

- [ ] Python engine fully replaces bash
- [ ] Rich TUI integrated into `owloop run`
- [ ] Preflight checks (claude availability, clean worktree, spec validation)
- [ ] ANSI stripping for completion signal detection
- [ ] Subprocess timeout (30min no-output kill)
- [ ] PyPI release (`uvx owloop` works)
- [ ] Basic test suite
- [ ] `owloop report` — lavish HTML summary after run

## v0.3 — Smart Specs

- [ ] `/owloop analyze` — scan codebase, generate problem report
- [ ] `/owloop-spec` v2 — auto-calibrate acceptance criteria against real baselines
- [ ] Spec-from-issue — convert Jira/GitHub issues to specs
- [ ] Spec-from-review — convert code review findings to specs

## v0.4 — Multi-Agent

- [ ] Agent adapter for Codex CLI
- [ ] Agent adapter for OpenCode
- [ ] Parallel spec execution (multiple agents on different specs)
- [ ] Cross-spec dependency tracking

## v1.0 — Production

- [ ] CI/CD pipeline (lint, test, publish)
- [ ] Comprehensive docs site
- [ ] skills.sh registration
- [ ] Community spec library (reusable spec templates)

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
