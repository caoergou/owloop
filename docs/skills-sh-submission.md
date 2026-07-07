# skills.sh Indexing Submission Record

## Submission

- **Issue URL**: https://github.com/vercel-labs/skills/issues/1586
- **Repository submitted**: https://github.com/caoergou/owloop
- **Submitted at**: 2026-07-06
- **Submitted by**: caoergou

## Skills included

The repository hosts 5 composable agent skills under `skills/`:

| Skill | Purpose |
|---|---|
| `owloop` | Core loop engineering methodology (agent-agnostic) |
| `owloop-spec` | Interactive spec-creation wizard with baseline calibration |
| `owloop-loop-control` | Promise protocol and loop convergence behavior |
| `owloop-verify` | Verification pipeline and automated code-review gate |
| `owloop-report` | Independent rich HTML report generation |

## Install command

```bash
npx skills add caoergou/owloop
```

## Status

- [x] Issue created at `vercel-labs/skills`
- [ ] Indexed by skills.sh maintainers
- [ ] Verifiable with `npx skills find owloop`

## Notes

- The skills follow the agentskills.io standard (`skills/<name>/SKILL.md`).
- They are designed to be agent-agnostic and work with Claude Code, Kimi Code CLI, Codex, Cursor, and other agents supported by `npx skills`.
- The associated owloop feature PR is at https://github.com/caoergou/owloop/pull/16.
