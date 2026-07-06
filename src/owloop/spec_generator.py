"""Natural-language goal clarification and spec drafting.

`owloop spec` turns a vague goal like "refactor error handling" into one or
more constraint-oriented specs. Large goals are automatically decomposed into
multiple ordered specs with dependency annotations.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from owloop.adapters import AgentAdapter
from owloop.backpressure import BackpressureDiscovery, load_backpressure
from owloop.paths import resolve_specs_dir
from owloop.promise import parse_promise_signal
from owloop.spec_queue import find_next_spec_number

SPEC_GENERATION_PROMPT = """\
# Owloop — Spec Generation Mode

You are helping the user turn a vague goal into concrete, runnable owloop specs.
A large goal MUST be decomposed into multiple ordered specs automatically.
You MUST use the full codebase scan + baseline calibration workflow below.

Read these files if they exist (in order):
1. `AGENTS.md` — agent instructions for this project
2. `CLAUDE.md` — coding conventions, architecture rules, tool commands

Then scan the entire codebase to understand the current state before making
assumptions. Use Glob/Grep/Read as needed. Do not skip this step.

The user's goal:
```
{goal}
```

Previous clarifications (if any):
{clarifications}

## Step 1 — Intent check
Restate the goal in one concrete, actionable sentence. If it is still vague
(e.g. "optimize", "improve", "refactor things"), output up to 3 focused
questions in this exact format, separated by ` | `:

<promise>DECIDE:Which module should I optimize? | What metric defines success? | Which test command proves the change is correct?</promise>

## Step 2 — Feasibility gate
Decide whether "done" can be expressed as shell commands that return pass/fail.
- If NO → explain why and output `<promise>DECIDE:...>` with the blocking question.
- If YES → continue to Step 3.

## Step 3 — Scope analysis & decomposition
Identify ALL files/directories involved and estimate the total scope.

**If the total scope is ≤ 5 files / < 300 lines**: write a single spec (skip to Step 4).

**If the total scope is larger**: decompose into multiple specs. Each spec should:
- Touch 1-5 files / < 300 lines
- Be independently verifiable (has its own acceptance criteria)
- Have a clear dependency order (which specs must complete first)

Plan the decomposition as an ordered list before writing any spec. Common
decomposition patterns:
- Scan/analyze → Extract/refactor → Integrate → Verify
- Module A → Module B → Module C (independent modules in parallel priority)
- Create abstractions → Migrate consumers → Clean up old code

## Step 4 — Baseline calibration
Before writing acceptance criteria, run the proposed verification commands NOW
and record the current values. Scan `pyproject.toml`, `package.json`, `Makefile`,
and README to find the correct test/lint/build commands.

This project already has the following discovered verification commands (from
`.owloop/backpressure.json`). Prefer these commands for acceptance criteria:

{backpressure_commands}

Record the baseline in a `## Baseline` section, e.g.:
- `ruff check src/`: 84 errors at start, target ≤ 5
- `pytest tests/`: 3 failures at start, target 0 failures

## Step 5 — Constraints
Define concrete Exclusions (files/modules that must NOT be touched) and Style
rules. Exclusions must name specific files or directories, not generic rules.

## Step 6 — Stuck behavior
Choose one stuck-behavior instruction and include it verbatim in each spec:
1. Document and move on: "If you cannot make progress after 2 attempts at the
   same error, add a `## Blockers` section to this spec describing what's
   blocking you, commit your partial work, and output `<promise>DONE</promise>`."
2. Partial commit: "If only some acceptance criteria pass, commit the passing
   changes, update the acceptance criteria to reflect remaining work, and
   output `<promise>DONE</promise>`."
3. Revert and stop: "If tests fail after implementation, `git checkout .` to
   revert all changes and output `<promise>DONE</promise>` with a note about
   what went wrong."

## Step 7 — Write the spec(s)
Write ALL specs in a single response, separated by `---` on its own line.
Each spec uses this exact structure:

```markdown
# Spec: [short kebab-case name]

## Priority: [1-5, lower = higher priority]

## Depends On
- [list spec names this depends on, or "none"]

## Requirements
- [ ] Concrete, scoped task description
- [ ] Search the codebase for existing implementations before creating new ones

## Acceptance Criteria
- [ ] `exact shell command` → expected pass/fail behavior or concrete output
- [ ] `exact shell command` → expected pass/fail behavior or concrete output

## Exclusions
- Do NOT modify [specific files/directories]
- Do NOT change external API behavior
- Do NOT modify pyproject.toml, uv.lock, or other config files
- Do NOT modify, delete, or comment out existing tests

## Style
- Follow existing project conventions (name the specific adjacent file/pattern)

## Stuck Behavior
- [Chosen instruction from Step 6]

## Verification
Run the acceptance criteria commands after each change.

## Baseline
- [Recorded baselines from Step 4]

Output when complete: `<promise>DONE</promise>`
```

## Step 8 — Self-check before outputting
Verify for EACH spec:
- Every acceptance criterion is a runnable shell command with a concrete expected output.
- The Exclusions section is non-empty and names specific files/directories.
- Scope is 1-5 files / < 300 lines per spec.
- Baseline was recorded and targets are realistic.
- Dependencies are correctly stated (later specs reference earlier ones).

If all specs pass the self-check, end your response with `<promise>DONE</promise>`
on its own line. If you need clarification, use only the `<promise>DECIDE:...>` line.
"""

SPEC_FILENAME_RE = re.compile(r"#\s*Spec:\s*(.+)", re.IGNORECASE)


class SpecGenerationError(Exception):
    """Raised when spec generation cannot produce a valid spec file."""


class SpecGenerator:
    """Generate one or more specs from a natural-language goal."""

    def __init__(self, project_dir: Path, adapter: AgentAdapter) -> None:
        self.project_dir = project_dir
        self.adapter = adapter
        self.clarifications: list[str] = []

    def _build_prompt(self, goal: str) -> str:
        clarifications_text = ""
        if self.clarifications:
            clarifications_text = "\n".join(
                f"- {entry}" for entry in self.clarifications
            )
        else:
            clarifications_text = "(none yet)"

        commands = load_backpressure(self.project_dir)
        if not commands:
            commands = BackpressureDiscovery(self.project_dir).discover()

        if commands:
            backpressure_text = "\n".join(
                f"- `{cmd.command}` ({cmd.name}, from {cmd.source})"
                for cmd in commands
            )
        else:
            backpressure_text = "(none discovered; infer commands from project files)"

        return SPEC_GENERATION_PROMPT.format(
            goal=goal,
            clarifications=clarifications_text,
            backpressure_commands=backpressure_text,
        )

    def _ask_user(self, questions: list[str]) -> list[str]:
        """Present questions in the terminal and collect answers."""
        answers: list[str] = []
        print(f"\nNeed clarification ({len(questions)} question{'s' if len(questions) > 1 else ''}):\n")
        for i, question in enumerate(questions, 1):
            print(f"{i}. {question.strip()}")
            try:
                answer = input("   > ").strip()
            except EOFError:
                answer = ""
            answers.append(answer)
        return answers

    def _parse_questions(self, payload: str) -> list[str]:
        """Split a DECIDE payload into individual questions."""
        raw = payload.split("|")
        questions = [q.strip() for q in raw if q.strip()]
        return questions[:3]

    def _extract_spec_markdown(self, text: str) -> str:
        """Extract the markdown spec from agent output, stripping the promise line."""
        lines = text.splitlines()
        result: list[str] = []
        for line in lines:
            if "<promise>" in line and "</promise>" in line:
                continue
            result.append(line)
        return "\n".join(result).strip()

    def _split_specs(self, text: str) -> list[str]:
        """Split multi-spec output on `---` separator lines."""
        raw = self._extract_spec_markdown(text)
        chunks = re.split(r"\n---+\n", raw)
        specs = []
        for chunk in chunks:
            chunk = chunk.strip()
            if "# Spec:" in chunk and "## Acceptance Criteria" in chunk:
                specs.append(chunk)
        return specs if specs else ([raw] if "# Spec:" in raw else [])

    def _spec_name_from_markdown(self, markdown: str) -> str:
        """Derive a filename-safe spec name from the markdown title."""
        match = SPEC_FILENAME_RE.search(markdown)
        if match:
            raw = match.group(1).strip()
            return re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
        return "clarified-goal"

    def generate(
        self,
        goal: str,
        *,
        max_rounds: int = 3,
        ask_fn: Callable[[list[str]], list[str]] | None = None,
        on_line: Callable[[str], None] | None = None,
    ) -> list[Path]:
        """Run the clarification loop and write spec file(s).

        A large goal is automatically decomposed into multiple ordered specs.

        Returns:
            List of paths to written spec files (one or more).
        """
        ask_fn = ask_fn or self._ask_user

        for _round in range(max_rounds):
            prompt = self._build_prompt(goal)
            result = self.adapter.run(prompt, cwd=self.project_dir, on_line=on_line)
            clean_output = result.stdout

            parsed = parse_promise_signal(clean_output)
            if parsed is None:
                specs = self._split_specs(clean_output)
                if specs:
                    return self._write_specs(specs)
                raise SpecGenerationError(
                    "agent did not return a recognizable spec or clarification request"
                )

            state, payload = parsed
            if state == "DONE":
                specs = self._split_specs(clean_output)
                if specs:
                    return self._write_specs(specs)
                raise SpecGenerationError(
                    "agent returned DONE but no valid spec was found in the output"
                )

            if state == "DECIDE":
                questions = self._parse_questions(payload)
                if not questions:
                    raise SpecGenerationError(
                        "agent asked for clarification but provided no questions"
                    )
                answers = ask_fn(questions)
                for q, a in zip(questions, answers, strict=True):
                    self.clarifications.append(f"Q: {q}\n   A: {a}")
                continue

            raise SpecGenerationError(f"unexpected promise state: {state}")

        raise SpecGenerationError(
            f"could not clarify the goal after {max_rounds} rounds; "
            "try describing the task more concretely"
        )

    def _write_specs(self, spec_markdowns: list[str]) -> list[Path]:
        """Write one or more spec files with sequential numbering."""
        specs_dir = resolve_specs_dir(self.project_dir)
        specs_dir.mkdir(parents=True, exist_ok=True)

        paths: list[Path] = []
        number = find_next_spec_number(specs_dir)

        for markdown in spec_markdowns:
            slug = self._spec_name_from_markdown(markdown)
            padded = f"{number:02d}"
            spec_path = specs_dir / f"{padded}-{slug}.md"

            counter = 1
            original_path = spec_path
            while spec_path.exists():
                spec_path = original_path.with_suffix(f".{counter}.md")
                counter += 1

            spec_path.write_text(markdown + "\n", encoding="utf-8")
            paths.append(spec_path)
            number += 1

        return paths
