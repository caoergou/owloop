"""Natural-language goal clarification and spec drafting.

`owloop spec` turns a vague goal like "refactor error handling" into one or
more constraint-oriented specs. Large goals are automatically decomposed into
multiple ordered specs with dependency annotations.
"""

from __future__ import annotations

import re
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from owloop.adapters import AgentAdapter
from owloop.backpressure import BackpressureDiscovery, load_backpressure
from owloop.paths import resolve_specs_dir
from owloop.promise import parse_promise_signal
from owloop.spec_linter import Finding, SpecLinter
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
- [ ] Concrete, scoped task description. Prefer EARS-style phrasing where it
      fits — "WHEN <trigger>, THE SYSTEM SHALL <response>", "WHILE <state>, THE
      SYSTEM SHALL <response>", or "IF <condition> THEN THE SYSTEM SHALL
      <response>" — it maps cleanly onto shell-verifiable acceptance criteria.
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
Every generated spec MUST satisfy `SpecLinter` validation (the linter owloop
runs on every spec before the loop starts). It checks for backtick-quoted
shell commands in Acceptance Criteria, non-empty required sections, and more.
The linter's exact rules for this project:

{lint_rules}

Verify for EACH spec:
- Every acceptance criterion is a runnable shell command wrapped in a backtick
  (`` ` ``) and has a concrete expected output — this is required by the linter.
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

    def __init__(
        self,
        project_dir: Path,
        adapter: AgentAdapter,
        *,
        lint_retries: int = 1,
    ) -> None:
        """Initialize the generator.

        Args:
            project_dir: Root of the target project.
            adapter: Agent adapter used to run generation prompts.
            lint_retries: Max number of times to feed `SpecLinter` errors back
                to the agent and re-request a fixed spec before giving up and
                writing the last candidate as-is.
        """
        self.project_dir = project_dir
        self.adapter = adapter
        self.lint_retries = lint_retries
        self.clarifications: list[str] = []
        # Clarify gate (#36): questions the agent raised that no human answered
        # (non-interactive run). Recorded as a `## Assumptions` section in every
        # generated spec so the operator can audit them in the morning.
        self.assumptions: list[str] = []
        self._interactive = True
        self._linter = SpecLinter(resolve_specs_dir(project_dir), project_dir=project_dir)

    def _build_prompt(self, goal: str) -> str:
        clarifications_text = ""
        if self.clarifications:
            clarifications_text = "\n".join(
                f"- {entry}" for entry in self.clarifications
            )
        else:
            clarifications_text = "(none yet)"

        if not self._interactive:
            clarifications_text += (
                "\n\nNON-INTERACTIVE MODE: no human is available to answer "
                "questions. Do NOT stall on clarification — for any ambiguity, "
                "choose the most reasonable default and proceed. The loop records "
                "unresolved questions as a `## Assumptions` section for later audit."
            )

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
            lint_rules=self._linter.rules_summary(),
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
        interactive: bool | None = None,
    ) -> list[Path]:
        """Run the clarification loop and write spec file(s).

        A large goal is automatically decomposed into multiple ordered specs.

        The clarify gate (#36) behaves two ways: interactively it asks the user
        the agent's clarifying questions; non-interactively it records each
        question as an assumption (the agent picks a default) and appends a
        ``## Assumptions`` section to every generated spec so the human can
        audit those choices later. ``interactive`` defaults to whether stdin is
        a TTY.

        Returns:
            List of paths to written spec files (one or more).
        """
        ask_fn = ask_fn or self._ask_user
        self._interactive = sys.stdin.isatty() if interactive is None else interactive

        for _round in range(max_rounds):
            prompt = self._build_prompt(goal)
            result = self.adapter.run(prompt, cwd=self.project_dir, on_line=on_line)
            clean_output = result.stdout

            parsed = parse_promise_signal(clean_output)
            if parsed is None:
                specs = self._split_specs(clean_output)
                if specs:
                    specs = self._lint_and_retry(specs, on_line)
                    return self._write_specs(self._apply_assumptions(specs))
                raise SpecGenerationError(
                    "agent did not return a recognizable spec or clarification request"
                )

            state, payload = parsed
            if state == "DONE":
                specs = self._split_specs(clean_output)
                if specs:
                    specs = self._lint_and_retry(specs, on_line)
                    return self._write_specs(self._apply_assumptions(specs))
                raise SpecGenerationError(
                    "agent returned DONE but no valid spec was found in the output"
                )

            if state == "DECIDE":
                questions = self._parse_questions(payload)
                if not questions:
                    raise SpecGenerationError(
                        "agent asked for clarification but provided no questions"
                    )
                if not self._interactive:
                    # No human to answer: record the questions as assumptions the
                    # agent must resolve with defaults, and loop again with the
                    # non-interactive directive so it proceeds to write specs.
                    for q in questions:
                        self.assumptions.append(q)
                        self.clarifications.append(
                            f"Q: {q}\n   A: (no human available — choose a reasonable default)"
                        )
                    continue
                answers = ask_fn(questions)
                for q, a in zip(questions, answers, strict=True):
                    self.clarifications.append(f"Q: {q}\n   A: {a}")
                continue

            raise SpecGenerationError(f"unexpected promise state: {state}")

        raise SpecGenerationError(
            f"could not clarify the goal after {max_rounds} rounds; "
            "try describing the task more concretely"
        )

    def _apply_assumptions(self, specs: list[str]) -> list[str]:
        """Append a ``## Assumptions`` section to each spec (non-interactive gate).

        Deduplicated, in first-seen order. No-op when nothing was assumed (e.g.
        an interactive run or a goal the agent never needed to clarify).
        """
        if not self.assumptions:
            return specs
        unique = list(dict.fromkeys(self.assumptions))  # de-dup, preserve order
        block = "## Assumptions\n" + "\n".join(
            f"- {q} — resolved with a default; audit before relying on it." for q in unique
        )
        return [self._insert_assumptions_section(spec, block) for spec in specs]

    @staticmethod
    def _insert_assumptions_section(markdown: str, block: str) -> str:
        """Insert an Assumptions section ahead of Verification (or append it)."""
        if "## Assumptions" in markdown:
            return markdown
        match = re.search(r"^##\s+Verification\s*$", markdown, re.MULTILINE)
        if match:
            idx = match.start()
            return markdown[:idx] + block + "\n\n" + markdown[idx:]
        return markdown.rstrip() + "\n\n" + block + "\n"

    def _lint_candidate(self, markdown: str) -> list[Finding]:
        """Lint a candidate spec's markdown before it is written to disk.

        Writes the candidate to a scratch file so `SpecLinter.lint_spec()`
        can be reused as-is rather than duplicating its checks.
        """
        with tempfile.TemporaryDirectory() as scratch_dir:
            scratch_path = Path(scratch_dir) / "candidate.md"
            scratch_path.write_text(markdown + "\n", encoding="utf-8")
            linter = SpecLinter(scratch_path.parent, project_dir=self.project_dir)
            return linter.lint_spec(scratch_path)

    def _build_lint_feedback_prompt(self, errors_by_spec: dict[str, list[Finding]]) -> str:
        """Build a follow-up prompt asking the agent to fix lint errors."""
        sections = []
        for spec, errors in errors_by_spec.items():
            match = SPEC_FILENAME_RE.search(spec)
            title = match.group(1).strip() if match else "spec"
            error_lines = "\n".join(f"- {finding.message}" for finding in errors)
            sections.append(f"### {title}\n{error_lines}")
        errors_text = "\n\n".join(sections)

        return (
            "The spec(s) you generated failed `SpecLinter` validation. Fix ONLY "
            "the listed errors and re-output ALL specs in the same format as "
            "before (one or more `# Spec:` blocks, separated by `---` on its "
            "own line if there is more than one), ending with "
            f"`<promise>DONE</promise>`.\n\nLint errors:\n\n{errors_text}"
        )

    def _lint_and_retry(
        self,
        specs: list[str],
        on_line: Callable[[str], None] | None,
    ) -> list[str]:
        """Lint each candidate spec and retry generation on lint errors.

        Retries up to `self.lint_retries` times. If errors remain after the
        last retry, the last candidate specs are returned as-is so the loop
        does not stall indefinitely on an agent that cannot self-correct.
        """
        current = specs
        for _attempt in range(self.lint_retries):
            errors_by_spec = {
                spec: errors
                for spec in current
                if (errors := [f for f in self._lint_candidate(spec) if f.severity == "error"])
            }
            if not errors_by_spec:
                return current

            feedback_prompt = self._build_lint_feedback_prompt(errors_by_spec)
            result = self.adapter.run(feedback_prompt, cwd=self.project_dir, on_line=on_line)
            retried_specs = self._split_specs(result.stdout)
            if not retried_specs:
                return current
            current = retried_specs

        return current

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
