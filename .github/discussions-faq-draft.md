# Draft: FAQ Discussion post

- Target: GitHub Discussions, category **Q&A** (`DIC_kwDOTLjf0c4DAZVs`)
- Title: `FAQ: When to use owloop?`
- Status: draft only — not yet posted (needs direct user go-ahead)

---

Common questions about when and how to use **owloop**.

## When to use owloop vs `/goal`?

`/goal` (interactive, single-session planning/execution inside a Claude Code conversation) is best when you want to stay in the loop, review each step, and steer as you go. **owloop** is for unattended, multi-iteration work: you write a spec with shell-verifiable acceptance criteria, kick off the loop, and walk away — each iteration spawns a fresh `claude -p --permission-mode auto` process, verifies the criteria, and only commits on success. Use `/goal` when you want to co-drive; use owloop when you want to hand off a well-scoped, objectively verifiable task and check back later (e.g., overnight).

## When to use owloop vs gnhf?

They target different failure modes. gnhf-style "get nudged, hold fast"-type wrappers generally help keep a single agent session on track during one sitting. owloop is built around **worktree isolation + fresh context per iteration** — every loop round starts a brand-new process with zero memory of prior rounds, and all state lives on disk (`specs/`, `logs/`, `IMPLEMENTATION_PLAN.md`). Reach for owloop specifically when a task benefits from many independent attempts against the same spec, run over hours or overnight, without accumulating conversational drift.

## What tasks work well with owloop?

Tasks that can be reduced to **objective, shell-verifiable acceptance criteria** — things like:
- Bug fixes with a reproducible failing test
- Adding test coverage to hit a coverage threshold
- Mechanical refactors/migrations with a clear "done" signal (build passes, lints pass, tests pass)
- Well-scoped feature additions where "done" is a command that exits 0

Tasks that work poorly: open-ended design decisions, anything requiring human taste/judgment calls mid-stream, or work where "correct" can't be checked by a script.

## Is owloop safe for production code?

owloop runs in **Auto Mode, not YOLO** — it always launches Claude Code with `--permission-mode auto`, never `--dangerously-skip-permissions`. Combined with git worktree isolation, each iteration operates in its own workspace, and changes only land via normal commits after acceptance criteria pass. That said, owloop is a loop *engine*, not a safety net for bad specs — always review the resulting commits before merging to your main branch, and treat the constitution/spec's "Exclusions" section as your primary guardrail against the loop wandering into places you didn't intend.

## How do I write good specs for owloop?

A good owloop spec has five parts, all shell-verifiable where possible:
1. **Requirements** — what needs to be built, in plain language
2. **Acceptance Criteria** — concrete shell commands the loop runs to confirm success (tests pass, a script exits 0, a file exists with expected content, etc.)
3. **Exclusions** — explicitly out-of-bounds files, directories, or approaches; this is what keeps an unattended loop from wandering off-spec
4. **Style** — conventions to follow (naming, formatting, existing patterns to mirror)
5. **Verification** — how a human should double check the result before trusting it

Never skip Exclusions — it's the single most important section for keeping a multi-hour unattended run on track.
