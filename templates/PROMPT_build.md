# Owloop — Build Mode

You are running inside an Owloop autonomous loop.

Read these files if they exist (in order):
1. `AGENTS.md` — agent instructions for this project
2. `CLAUDE.md` — coding conventions, architecture rules, tool commands

Find the highest-priority incomplete work item in specs/, implement it completely,
verify all acceptance criteria by running the shell commands specified in the spec,
add a `**Status**: COMPLETE` line near the top of that spec's markdown file,
commit and push, then output `<promise>DONE</promise>`.

Before implementing, search the codebase for existing implementations — do not
assume something doesn't exist without checking.

ONLY modify files within the scope described in the spec's Requirements section.
Do NOT touch files listed in the spec's Exclusions section.
Do NOT modify, delete, or comment out existing tests.
