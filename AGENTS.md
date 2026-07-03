# Agent Instructions

Read `CLAUDE.md` for contributor guidance on the owloop codebase.

## If running inside an owloop loop

You are in **autonomous loop mode**. Follow these rules:

1. Read `specs/` and pick the highest-priority incomplete spec (lowest number first)
2. Implement it completely within the scope defined in the spec
3. Verify all acceptance criteria by running the shell commands in the spec
4. Add `**Status**: COMPLETE` near the top of the spec file
5. Commit and push
6. Output `<promise>DONE</promise>` — the loop checks for this exact string

Do NOT touch files listed in the spec's Exclusions section.
