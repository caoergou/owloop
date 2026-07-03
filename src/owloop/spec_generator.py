"""Natural-language goal clarification and spec drafting.

`owloop spec` turns a vague goal like "refactor error handling" into a
constraint-oriented spec by asking the agent to study the codebase, surface
ambiguities as questions, and finally write a concrete `specs/NNN-*.md` file.
"""

from __future__ import annotations

import re
from pathlib import Path

from owloop.adapters import AgentAdapter
from owloop.promise import parse_promise_signal
from owloop.spec_queue import find_next_spec_number

SPEC_GENERATION_PROMPT = """\
# Owloop — Spec Generation Mode

You are helping the user turn a vague goal into a concrete, runnable owloop spec.

Read these files if they exist (in order):
1. `AGENTS.md` — agent instructions for this project
2. `CLAUDE.md` — coding conventions, architecture rules, tool commands

Search the codebase to understand the current state before making assumptions.

The user's goal:
```
{goal}
```

Previous clarifications (if any):
{clarifications}

## Your task

Decide whether the goal is already concrete enough to write a spec, or whether
you need clarifying answers.

### If you need clarification

Output up to 3 focused questions in this exact format, separated by ` | `:

<promise>DECIDE:What concrete error patterns should be unified? | Should the public API surface stay unchanged? | Which test command proves the refactor is correct?</promise>

Questions must be specific and informed by the codebase. Do not ask things you
could determine by reading the code.

### If the goal is concrete enough

Write a complete owloop spec in markdown. Use this exact structure:

```markdown
# Spec: my-feature

## Priority: 3

## Requirements
- [ ] What to do (concrete, scoped)

## Acceptance Criteria
- [ ] `exact shell command` → expected pass/fail behavior
- [ ] `exact shell command` → expected output

## Exclusions
- Do NOT modify files outside the scope described above
- Do NOT change external API behavior
- Do NOT modify pyproject.toml, uv.lock, or other config files
- Do NOT modify existing tests

## Style
- Follow existing project conventions

## Verification
Run the acceptance criteria commands after each change.

## Assumptions
- Any assumptions you made while turning the vague goal into this spec

Output when complete: `<promise>DONE</promise>`
```

The acceptance criteria must be executable shell commands. Avoid subjective
language like "improve" or "better"; use pass/fail checks.

If you write the spec, end your response with `<promise>DONE</promise>` on its
own line. If you need clarification, use only the `<promise>DECIDE:...>` line.
"""

SPEC_FILENAME_RE = re.compile(r"#\s*Spec:\s*(.+)", re.IGNORECASE)


class SpecGenerationError(Exception):
    """Raised when spec generation cannot produce a valid spec file."""


class SpecGenerator:
    """Generate a spec from a natural-language goal via agent interaction."""

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
        return SPEC_GENERATION_PROMPT.format(
            goal=goal,
            clarifications=clarifications_text,
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
        ask_fn: callable | None = None,
    ) -> Path:
        """Run the clarification loop and write a spec file.

        Args:
            goal: The user's vague natural-language goal.
            max_rounds: Maximum clarification rounds before giving up.
            ask_fn: Optional override for asking questions (used in tests).

        Returns:
            Path to the written spec file.

        Raises:
            SpecGenerationError: if no spec could be generated.
        """
        ask_fn = ask_fn or self._ask_user

        for _round in range(max_rounds):
            prompt = self._build_prompt(goal)
            result = self.adapter.run(prompt, cwd=self.project_dir)
            clean_output = result.stdout

            parsed = parse_promise_signal(clean_output)
            if parsed is None:
                # No explicit signal: if the output looks like a spec, accept it;
                # otherwise treat it as an error.
                markdown = self._extract_spec_markdown(clean_output)
                if "# Spec:" in markdown and "## Acceptance Criteria" in markdown:
                    return self._write_spec(markdown)
                raise SpecGenerationError(
                    "agent did not return a recognizable spec or clarification request"
                )

            state, payload = parsed
            if state == "DONE":
                markdown = self._extract_spec_markdown(clean_output)
                return self._write_spec(markdown)

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

    def _write_spec(self, markdown: str) -> Path:
        specs_dir = self.project_dir / "specs"
        specs_dir.mkdir(parents=True, exist_ok=True)

        slug = self._spec_name_from_markdown(markdown)
        number = find_next_spec_number(specs_dir)
        padded = f"{number:02d}"
        spec_path = specs_dir / f"{padded}-{slug}.md"

        # Avoid overwriting an existing file by appending a suffix.
        counter = 1
        original_path = spec_path
        while spec_path.exists():
            spec_path = original_path.with_suffix(f".{counter}.md")
            counter += 1

        spec_path.write_text(markdown + "\n", encoding="utf-8")
        return spec_path
