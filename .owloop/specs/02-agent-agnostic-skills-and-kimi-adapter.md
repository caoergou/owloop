# Spec: Agent-agnostic skills system and Kimi runtime support

**Status**: COMPLETE

## Priority: 2

## Depends On
- none (can proceed in parallel with existing work)

## Requirements

1. Make the owloop skill content agent-agnostic so it works well across Claude Code, Kimi Code CLI, and any other agentskills.io-compatible agent.
2. Add a `KimiCodeAdapter` to `src/owloop/adapters.py` so the owloop engine can drive Kimi Code CLI as the loop agent.
3. Update installation documentation to show both Claude Code and Kimi Code CLI install paths.
4. Prepare and submit a skills.sh indexing request issue to `vercel-labs/skills`.

## Acceptance Criteria

- [x] `npx skills add caoergou/owloop --agent '*' --yes --global` installs the skills to both `~/.claude/skills/` and `~/.agents/skills/` without errors.
- [x] `npx skills add . --list` discovers 4 skills: `owloop`, `owloop-spec`, `owloop-loop-control`, `owloop-verify`.
- [x] `skills/owloop/SKILL.md` no longer contains agent-specific commands like `claude -p`; it refers to "your agent's non-interactive prompt mode".
- [x] `uv run pytest tests/test_adapters.py -q` passes with new `KimiCodeAdapter` tests.
- [x] `uv run owloop run --help` shows `--agent [claude|kimi]`.
- [x] A pull request is created at `caoergou/owloop` to deliver the skill refactor and Kimi adapter tests.
- [ ] A GitHub issue titled `Request to index skill: caoergou/owloop` is created at `vercel-labs/skills` and returns a valid issue URL (pending user confirmation).
- [ ] `curl -s "https://skills.sh/api/search?q=owloop"` returns `count > 0` after indexing (depends on maintainers).

## Exclusions

- Do NOT remove or break the existing `ClaudeCodeAdapter`.
- Do NOT change the core loop engine logic in `engine.py` beyond adding the new adapter selection path.
- Do NOT modify the Python package distribution or PyPI publishing flow.
- Do NOT add new dependencies beyond what is already required by the existing adapter pattern.
- Do NOT touch unrelated tests in `tests/`.

## Style

- Follow the existing adapter pattern in `src/owloop/adapters.py` (ABC interface, `preflight()`, `run()`, `name`).
- Keep SKILL.md language policy: respond in user's language, spec section headers in English.
- Maintain the existing project tone: professional, terse, constraint-oriented.

## Stuck Behavior

If Kimi's `--auto` flag semantics differ from Claude's `--permission-mode auto` and cannot be mapped safely, document the difference in `references/kimi-adapter-notes.md` and leave the adapter disabled behind a feature flag rather than silently using a more permissive mode.

## Verification

Run the acceptance criteria commands after each change. For the GitHub issue, verify the issue URL is reachable and contains the required indexing request information.

## Baseline

- Current `npx skills find owloop` returns `No skills found for "owloop"`.
- Current `npx skills add caoergou/owloop --agent '*'` installs only to `~/.claude/skills/owloop` by default; `~/.agents/skills/owloop` is not populated unless explicitly requested with `--agent '*'`.
- Current `src/owloop/adapters.py` only supports `claude` and `mock` agents.
