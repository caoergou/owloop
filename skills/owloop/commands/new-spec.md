---
name: owloop-spec
description: >-
  Interactive wizard to create high-quality, constraint-oriented Owloop specs
  with baseline calibration and pre-flight validation —
  创建高质量 Owloop spec 的交互式向导，含基线校准和预检验证。
  Use when user says "create a spec", "write a spec", "new spec",
  "帮我写 spec", "新建 spec", "创建规范".
---

# Interactive Owloop Spec Creation

**Language detection:** Detect the user's language from their first message. Conduct the entire interview in that language. Section headers in the generated spec file are always English (`## Requirements`, `## Exclusions`, etc.).

Guide the user through a structured interview to produce a spec that **converges instead of looping forever**. The process has 7 steps: intent → feasibility gate → scope & sizing → baseline calibration → constraints → stuck behavior → generate & validate.

For loop engineering best practices, see [references/loop-engineering-guide.md](../references/loop-engineering-guide.md).

---

## Step 1: One-sentence intent

Ask:

> What should the agent do? Describe it in one sentence.
>
> （你想让 agent 做什么？用一句话描述。）

Do not proceed until you have a specific, actionable description. If the answer is too vague (e.g., "optimize the code", "improve performance", "refactor things"), ask once more for a concrete goal: which feature, what problem, why it matters.

---

## Step 2: Feasibility gate

Before investing in a full spec, validate that this task is suitable for an autonomous loop. Ask yourself (do NOT ask the user all of these — make the judgment, then confirm or redirect):

**The critical question:** Can "done" be expressed as a shell command that returns pass/fail?

- If YES → proceed to Step 3.
- If NO (requires human judgment, design decisions, UI review) → tell the user this task isn't a good fit for owloop and suggest doing it interactively instead. Be specific about WHY.

**Red flags that signal a bad fit:**
- "Make it look good" / "Improve the UX" — subjective
- "Optimize performance" without a specific metric — unmeasurable
- "Refactor the architecture" without a target design — open-ended
- Security-sensitive changes — too risky for unattended execution

If you're unsure, ask the user: "How would you verify this is done? Is there a command you could run?" / "怎么验证做完了？有没有能跑的命令？" — their answer tells you whether this belongs in owloop.

---

## Step 3: Scope & sizing

Ask about scope, but also actively validate the task size:

> Which files/directories does this involve? Roughly how many files will change?
>
> （涉及哪些文件/目录？大概会改多少个文件？）

**Sizing validation** (do this silently, then share your assessment):

| Size signal | Assessment | Action |
|---|---|---|
| 1-3 files, < 100 lines | Ideal | Proceed |
| 4-5 files, 100-300 lines | Good, but watch scope | Proceed with tight exclusions |
| 6+ files or 300+ lines | Too large — likely to drift or loop | Suggest splitting into 2-3 specs |
| "The whole project" | Way too large | Push back: "Which specific module or pattern first?" |

If the task is too large, help the user decompose it. Example: "Extract ValidationError handling" can be split into: (1) extract the handler function, (2) wire it into the app factory, (3) remove the old try/except blocks.

---

## Step 4: Baseline calibration

This is the step most people skip — and it's what separates specs that converge from specs that loop forever.

**Before writing acceptance criteria, run the proposed verification commands NOW.** Scan the repo for existing test/lint/build commands first (`pyproject.toml`, `package.json`, `Makefile`, README).

```bash
# Example: user wants to reduce ruff errors
uv run ruff check backend/ 2>&1 | tail -1
# → "Found 84 errors."
# Baseline: 84. Target: ≤ 5. This is achievable.

# Example: user wants all tests to pass
uv run pytest tests/ 2>&1 | tail -1
# → "3 failed, 47 passed"
# Baseline: 3 failures. If those failures are in the scope, good.
# If they're pre-existing and unrelated, the spec will never pass.
```

Share the baseline results with the user and confirm the target together:

> I ran the verification commands. Here's the current state:
> - `ruff check`: 84 errors
> - `pytest`: 3 failures (in test_auth.py — are these in scope?)
>
> What should the target be?

**What calibration catches:**
- **Already-passing criteria** → the loop exits on iteration 1 without doing real work (wasted run)
- **Broken infrastructure** → pytest crashes on import → the loop can NEVER pass
- **Unrealistic targets** → 84 errors → 0 in one spec is too ambitious; suggest ≤ 20 first
- **Pre-existing failures** → tests that fail before your change → the spec is doomed unless you exclude them

---

## Step 5: Constraints (Exclusions + Style)

Ask these two questions. For each, provide a reasonable default based on what you observe in the repo. The user confirms or corrects.

### 5a. Exclusions

> What must NOT be touched? Which files, modules, or behaviors are off-limits?
>
> （有哪些绝对不能碰的东西？）

If the user draws a blank, proactively suggest based on the scope:
- Database schema / migrations
- Public API response formats (status codes, JSON shape)
- Config files (`pyproject.toml`, `uv.lock`, `package.json`, `package-lock.json`)
- Unrelated modules (name the specific directories that are adjacent but out of scope)
- Existing tests: "Do NOT modify, delete, or comment out existing tests"

**This is the highest-leverage section.** Without explicit exclusions, the agent WILL "improve" things outside scope. Never skip or leave empty.

### 5b. Style

> Any coding conventions to follow?
>
> （项目有什么编码风格约定？）

Scan involved files and suggest: "Follow the pattern in `[adjacent_file]`" as a default.

---

## Step 6: Stuck behavior

Most specs skip this entirely — and it's why runs burn tokens on infinite retries.

Present the user with options (suggest the most appropriate one based on task type):

> What should the agent do if it gets stuck and can't make progress?
>
> （如果 agent 卡住了无法继续，应该怎么做？）

**Options:**

1. **Document and move on** (recommended for most tasks):
   "If you cannot make progress after 2 attempts at the same error, add a `## Blockers` section to this spec file describing what's blocking you, commit your partial work, and output `<promise>DONE</promise>`."

2. **Partial commit** (good for large cleanup tasks):
   "If only some acceptance criteria pass, commit the passing changes, update the acceptance criteria to reflect remaining work, and output `<promise>DONE</promise>`."

3. **Revert and stop** (good for risky changes):
   "If tests fail after implementation, `git checkout .` to revert all changes and output `<promise>DONE</promise>` with a note about what went wrong."

---

## Step 7: Generate spec file

With all information collected:

1. **Read the template**: Read `.owloop/templates/spec-template.md` (or fall back to `templates/spec-template.md` in legacy projects) for the canonical section structure.

2. **Generate a short name**: Extract a 2-4 word English kebab-case slug from the intent. Examples: `add-rate-limiting`, `fix-login-redirect`, `extract-validation-handler`.

3. **Determine file number** with consistent zero-padding:

   ```bash
   mkdir -p .owloop/specs
   last=$(find .owloop/specs -maxdepth 1 -type f -name '[0-9]*.md' 2>/dev/null \
     | sed -E 's#.*/([0-9]+)-.*#\1#' | sort -n | tail -1)

   if [ -z "$last" ]; then
     padded="001"
   else
     width=${#last}
     next_num=$((10#$last + 1))
     padded=$(printf "%0${width}d" "$next_num")
   fi
   ```

4. **Write the spec file** with all sections:

   - `# Spec: [title]` — from the intent (in user's language)
   - `## Priority: [1-5]` — default `3`
   - `## Requirements` — what to do, with "search the codebase for existing implementations before creating new ones"
   - `## Acceptance Criteria` — `- [ ] command → expected output` with calibrated targets from Step 4
   - `## Exclusions` — from Step 5a (must not be empty)
   - `## Style` — from Step 5b
   - `## Stuck Behavior` — from Step 6
   - `## Verification` — commands to run before completion (typically same as acceptance criteria)
   - `## Baseline` — record the calibration data from Step 4 (e.g., "ruff: 84 errors at start, target ≤ 5")
   - Last line: `Output when complete: <promise>DONE</promise>`

5. **Run the pre-flight validation checklist** silently before presenting:

   - [ ] Every acceptance criterion is a runnable shell command with a concrete expected output (no "works correctly")
   - [ ] Exclusions section is non-empty and names specific files/directories
   - [ ] No internal contradictions (e.g., "add type annotations" + "don't modify any .py files")
   - [ ] Scope matches the 1-5 file / < 300 line sweet spot
   - [ ] Baseline was recorded and target is realistic
   - [ ] Stuck behavior is defined

   If any item fails, fix it before presenting. If the fix requires user input, ask.

---

## Step 8: Review & confirm

Show the complete spec and the calibration summary:

> Here's the spec. Baseline calibration:
> - `ruff check`: 84 errors → target ≤ 5
> - `pytest`: 50 passed, 0 failed → must stay at 0 failures
>
> Does this look good? Any changes needed?
>
> （这份 spec 可以吗？需要调整哪里？）

- User confirms → done. Mention the file path and suggest:
  - "Run `owloop run` to start the loop"
  - "Recommended: watch the first 2-3 iterations to make sure the agent understands the task, then leave it running"
  - "运行 `owloop run` 启动循环。建议先看前 2-3 轮确认方向正确，再放手让它跑"
- User requests changes → edit and re-present. Repeat until confirmed.
