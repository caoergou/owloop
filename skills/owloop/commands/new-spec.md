---
name: owloop-spec
description: >-
  Interactive wizard to create constraint-oriented Owloop specs —
  创建 Owloop spec 的交互式向导。
  Use when user says "create a spec", "write a spec", "new spec",
  "帮我写 spec", "新建 spec", "创建规范".
---

# Interactive Owloop Spec Creation

**Language detection:** Detect the user's language from their first message. Conduct the entire interview and generate the spec in that language. Section headers in the generated spec file are always English (`## Requirements`, `## Exclusions`, etc.).

Guide the user through questions to produce a constraint-oriented spec file ready for the owloop loop.

The core of an owloop spec is **constraint-oriented**: Requirements alone aren't enough — the agent must know the scope, what's off-limits, and how to verify completion with shell commands. Without explicit Exclusions, an unattended loop will drift.

## Step 1: One-sentence intent

Ask the user:

> What should the agent do? Describe it in one sentence.
>
> （你想让 agent 做什么？用一句话描述。）

Do not proceed until you have a specific, actionable description. If the answer is too vague (e.g., "optimize the code", "improve performance", "refactor things"), ask once more for a concrete goal: which feature, what problem, why it matters.

## Step 2: Follow-up questions

Based on Step 1, ask these 4 questions. You may combine them into a single numbered list. For each, provide a reasonable default based on what you can observe in the repo (test commands from `pyproject.toml`/`package.json`/`Makefile`, coding patterns from adjacent files). The user confirms or corrects — don't make them think from scratch.

1. **Scope** — "Which files/directories are involved?" — must be specific paths, not "the whole project".
2. **Exclusions** — "What must NOT be touched?" — files, modules, behaviors. If the user draws a blank, suggest common exclusions: database schema, public API shapes, config files (`pyproject.toml`, `uv.lock`), unrelated modules. This is the most critical section — never skip or leave empty.
3. **Acceptance Criteria** — "How do we verify it's done? Any commands to run?" — target format: `command → expected output`. Before asking, scan the repo for existing test/lint/build commands and suggest them as defaults (e.g., "Should we use `uv run pytest` and `uv run ruff check`?").
4. **Style** — "Any coding conventions?" — scan involved files for patterns and suggest "follow the pattern in [file]" as a default.

## Step 3: Generate spec file

With all answers collected:

1. **Read the template**: Read `templates/spec-template.md` for the canonical section structure. Core structure: `# Feature: [name]` → `## Priority: [1-5]` → `## Requirements` → `## Acceptance Criteria` → `## Exclusions` → `## Style` → `## Verification` → final line `Output when complete: <promise>DONE</promise>`.

2. **Generate a short name**: Extract a 2-4 word English kebab-case slug from the intent (preserve technical terms like OAuth2, API). Examples: `add-rate-limiting`, `fix-login-redirect`.

3. **Determine file number** with consistent zero-padding (see `src/owloop/spec_queue.py` — specs are sorted lexicographically):

   ```bash
   mkdir -p specs
   last=$(find specs -maxdepth 1 -type f -name '[0-9]*.md' 2>/dev/null \
     | sed -E 's#.*/([0-9]+)-.*#\1#' | sort -n | tail -1)

   if [ -z "$last" ]; then
     padded="001"
   else
     width=${#last}
     next_num=$((10#$last + 1))
     padded=$(printf "%0${width}d" "$next_num")
   fi

   echo "specs/${padded}-<short-name>.md"
   ```

4. **Write the spec file** following the template structure:
   - `# Feature: [name]` — title from the intent (in the user's language)
   - `## Priority: [1-5]` — default `3`; `1` if user signals urgency; `5` if not urgent
   - `## Requirements` — what to do (from Step 1 + Step 2 scope)
   - `## Acceptance Criteria` — `- [ ] command → expected output` checklist (must be executable shell commands)
   - `## Exclusions` — specific files/directories/behaviors NOT to touch
   - `## Style` — coding conventions
   - `## Verification` — commands to run before completion (often overlaps with Acceptance Criteria)
   - Last line: `Output when complete: <promise>DONE</promise>` (the loop relies on this exact string)

## Step 4: Review and confirm

Show the complete file content and ask:

> Does this spec look good? Any changes needed?
>
> （这份 spec 可以吗？需要调整哪里？）

- User confirms → done. Mention the file path and that they can run `owloop run` to start.
- User requests changes → edit and show again. Repeat until confirmed.
