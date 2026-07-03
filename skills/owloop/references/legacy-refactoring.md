# Legacy Refactoring Reference

Target: read this when a spec involves refactoring old/legacy code.

## Sources & Confidence

- **Foundational (high confidence, cite as authority):**
  - Michael Feathers, *Working Effectively with Legacy Code* — characterization tests, seams, legacy code definition
  - Martin Fowler, *Refactoring* — safe mechanical patterns, strangler fig
  - Matthias Noback, Mikado Method articles
- **Validated production practice (high confidence):**
  - Shopify Engineering strangler-fig pattern case study
- **Empirical / community reports (medium confidence, use as supporting evidence):**
  - getunblocked.com/blog/refactoring-legacy-code/
  - codegeeks.solutions/blog/best-practices-for-ai-refactoring-legacy-code
  - arXiv studies on AI-assisted refactoring (cite as "empirical, mixed")
- **Prompt-engineering / skill catalogs (medium confidence, tactical phrases):**
  - antonioagudo.com/blog/the-magic-words-that-make-ai-code-better/
  - wondelai/skills (GitHub)

## Guidance Levels

Advice in this document is marked by strength:

- **Hard constraint** — do not override without explicit user approval.
- **Strong recommendation** — follow unless you have a clear, documented reason not to.
- **Heuristic** — a rule of thumb; adapt to the project context.

## When It Is Safe

- Tests pin the current behavior (characterization tests or existing regression tests).
- The change is small and reversible.
- Public contracts are protected — callers keep working.
- A rollback path exists: one `git revert` away from a clean state.

## Required Prep Steps

1. **Strong recommendation:** add characterization tests that capture current behavior before changing code.
2. Identify seams: interfaces, dependency injection points, or modules that can change in isolation.
3. Define blast radius: list the exact files and public symbols the spec may touch.
4. Record a baseline so progress can be measured.

## Heuristics for Targets

- Long files (>300 lines) are candidates for extraction, not automatic targets.
- Modules with high churn or many imports are often better split candidates than rarely touched code.
- Files with no test coverage should be treated as higher risk regardless of apparent simplicity.

## Safe Mechanical Patterns

- Extract method / function.
- Rename private symbols (not public interfaces).
- Inline trivial helpers.
- Encapsulate field access behind accessors.
- Remove dead code after confirming it is unreachable.
- Migrate syntax or types (e.g., Python 2 → 3, `typing` improvements).
- Update imports / paths to match moved modules.
- Apply lint fixes that do not change behavior.

## Patterns Requiring Human Judgment

- Architecture changes.
- API redesign or breaking changes.
- Business-logic changes.
- Security-sensitive code (auth, crypto, payments).
- Big-bang rewrites.

**Hard constraint:** if a spec asks for any of these, stop and ask the user for a blueprint or explicit approval before proceeding.

## Techniques

- **Characterization tests:** capture current output before changing anything.
- **Seams:** find boundaries where behavior can be safely redirected.
- **Mikado Method:** make a small change, see what breaks, draw a dependency graph, fix prerequisites first.
- **Strangler Fig:** incrementally replace legacy code by routing calls through a new facade.
- **Parallel run:** run old and new implementations side-by-side and compare outputs.
- **"No behavior change refactor" spell:** state explicitly that the only goal is equivalent behavior in a cleaner shape.

## Constraint Language for Specs

Use these phrases in specs to keep the run bounded:

- **Strong recommendation:** "Add characterization tests before changing behavior."
- **Hard constraint:** "Do not change public interfaces without explicit approval."
- **Heuristic:** "Keep blast radius to N files."
- **Hard constraint:** "Roll back must be one revert."
