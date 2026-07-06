"""AI-generated insights for owloop HTML reports.

`AIReportInsightsGenerator` reads the latest run summary, git history, diff
statistics, and spec files, then asks the coding agent to produce a structured
review report optimized for visualization in a Lavish-style artifact.

The output is not prose-first. It identifies the most complex and critical
changes, scores them by complexity and risk, and provides concrete review
suggestions so the HTML report can render cards, tables, and badges.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from owloop.adapters import AgentAdapter
from owloop.paths import resolve_logs_dir, resolve_specs_dir
from owloop.spec_queue import is_root_spec_complete

AI_REPORT_PROMPT = """\
You are producing a code-review artifact for an owloop autonomous coding run.
Your job is to identify the most complex and critical changes, score them, and
output structured data that will be rendered as cards, tables, and badges in an
HTML report.

Analyze the run summary, git history, diff statistics, and spec files below.
Do not summarize everything — focus on what actually matters for a human reviewer.

## Output rules

- Output ONLY a single JSON object matching the schema below.
- No markdown code fences. No commentary outside the JSON.
- Be concrete: name specific files, functions, or behaviors. Never write
  "check everything" or "ensure quality".
- Complexity and risk levels must be one of: low, medium, high.
- If a field has no meaningful content, use an empty list or empty string.

## JSON schema

{{
  "summary": "1-2 sentence overall verdict on the run outcome.",
  "key_changes": [
    {{
      "file": "path/to/file.py",
      "change_type": "refactor|add|remove|fix|migrate|other",
      "complexity": "low|medium|high",
      "risk_level": "low|medium|high",
      "description": "What changed, in one sentence.",
      "review_suggestions": ["specific thing to check", "another check"]
    }}
  ],
  "risks": [
    {{
      "level": "high|medium|low",
      "description": "Concrete risk tied to specific behavior or file.",
      "files": ["path/to/file.py"]
    }}
  ],
  "review_focus": [
    {{
      "priority": 1,
      "area": "Short name of the review area.",
      "reason": "Why this matters and what to look for."
    }}
  ],
  "next_actions": [
    {{
      "action": "What the reviewer should do next.",
      "urgency": "now|before_merge|nice_to_have"
    }}
  ]
}}

## Analysis guidelines

1. First identify every file that changed. Use the diff stat and commit log.
2. For each changed file, decide its change_type and complexity:
   - high: touches public API, threading, persistence, security, or many callers
   - medium: renames/extractions with moderate blast radius
   - low: cosmetic, dead-code removal, comment or import cleanup
3. Surface high-risk changes first in key_changes.
4. Risks must be specific: "Public API signature changed in module X" is good;
   "May break things" is bad.
5. Review focus should be ordered by priority (1 = most important).
6. Next actions should be actionable: commands, files to read, or tests to run.

## Inputs

### Run summary

```json
{summary_json}
```

### Git log (last {iterations} commits)

```
{git_log}
```

### Diff statistics

```
{diff_stat}
```

### Diff summary per file

```
{diff_files}
```

### Spec files

{specs_text}
"""



def _run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


@dataclass
class KeyChange:
    """A single changed file identified as complex or critical."""

    file: str
    change_type: str
    complexity: str
    risk_level: str
    description: str
    review_suggestions: list[str] = field(default_factory=list)


@dataclass
class Risk:
    """A concrete risk tied to changed files."""

    level: str
    description: str
    files: list[str] = field(default_factory=list)


@dataclass
class ReviewFocus:
    """A prioritized area for human review."""

    priority: int
    area: str
    reason: str


@dataclass
class NextAction:
    """A concrete next step for the reviewer."""

    action: str
    urgency: str


@dataclass
class ReportInsights:
    """Structured AI-generated content slots for the HTML report."""

    summary: str = ""
    key_changes: list[KeyChange] = field(default_factory=list)
    risks: list[Risk] = field(default_factory=list)
    review_focus: list[ReviewFocus] = field(default_factory=list)
    next_actions: list[NextAction] = field(default_factory=list)

    def has_content(self) -> bool:
        return bool(
            self.summary
            or self.key_changes
            or self.risks
            or self.review_focus
            or self.next_actions
        )


class AIReportInsightsGenerator:
    """Generate ReportInsights by asking the agent to review the run."""

    def __init__(self, project_dir: Path, adapter: AgentAdapter) -> None:
        self.project_dir = project_dir
        self.adapter = adapter

    def _load_summary(self) -> dict:
        summary_path = resolve_logs_dir(self.project_dir) / "owloop_summary_latest.json"
        if not summary_path.exists():
            raise FileNotFoundError(f"No run summary found at {summary_path}")
        with summary_path.open(encoding="utf-8") as f:
            return json.load(f)  # type: ignore[no-any-return]

    def _git_log(self, iterations: int) -> str:
        if iterations <= 0:
            return "(no commits)"
        result = _run_git(self.project_dir, "log", f"-{iterations}", "--oneline")
        return result.stdout.strip() if result.returncode == 0 else "(git log unavailable)"

    def _diff_stat(self, iterations: int) -> str:
        if iterations <= 0:
            return "(no diff)"
        result = _run_git(
            self.project_dir,
            "diff",
            "--stat",
            f"HEAD~{iterations}..HEAD",
        )
        return result.stdout.strip() if result.returncode == 0 else "(git diff unavailable)"

    def _diff_files(self, iterations: int) -> str:
        """Return per-file diff summaries for the changed files."""
        if iterations <= 0:
            return "(no diff)"
        result = _run_git(
            self.project_dir,
            "diff",
            "--stat",
            "--numstat",
            f"HEAD~{iterations}..HEAD",
        )
        if result.returncode != 0:
            return "(file diff unavailable)"
        lines = result.stdout.strip().splitlines()
        # --numstat output: insertions\tdeletions\tpath
        parts: list[str] = []
        for line in lines:
            if "\t" not in line:
                continue
            ins, dels, path = line.split("\t", 2)
            parts.append(f"{path}: +{ins} -{dels}")
        return "\n".join(parts) or "(no file-level diff)"

    def _specs_text(self) -> str:
        specs_dir = resolve_specs_dir(self.project_dir)
        if not specs_dir.is_dir():
            return "(no specs directory)"
        specs = sorted(specs_dir.glob("*.md"))
        if not specs:
            return "(no spec files)"
        parts: list[str] = []
        for spec in specs:
            content = spec.read_text(encoding="utf-8", errors="replace")
            status = "COMPLETE" if is_root_spec_complete(spec) else "INCOMPLETE"
            parts.append(f"### {spec.name} ({status})\n\n{content[:2000]}")
        return "\n\n---\n\n".join(parts)

    def _build_prompt(self, summary: dict) -> str:
        iterations = int(summary.get("iterations", 0))
        return AI_REPORT_PROMPT.format(
            summary_json=json.dumps(summary, indent=2),
            iterations=iterations,
            git_log=self._git_log(iterations),
            diff_stat=self._diff_stat(iterations),
            diff_files=self._diff_files(iterations),
            specs_text=self._specs_text(),
        )

    @staticmethod
    def _extract_json_object(text: str) -> str:
        """Extract the first top-level JSON object from text by brace counting."""
        start = text.find("{")
        if start == -1:
            raise ValueError("agent did not return a JSON object")
        depth = 0
        in_string = False
        escape = False
        for i, char in enumerate(text[start:], start=start):
            if escape:
                escape = False
                continue
            if char == "\\" and in_string:
                escape = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
        raise ValueError("agent did not return a balanced JSON object")

    @staticmethod
    def _parse_json_output(text: str) -> dict:
        """Extract and parse the JSON object from agent output."""
        obj_text = AIReportInsightsGenerator._extract_json_object(text)
        try:
            return json.loads(obj_text)  # type: ignore[no-any-return]
        except json.JSONDecodeError as exc:
            raise ValueError(f"agent returned invalid JSON: {exc}") from exc

    @staticmethod
    def _normalize_level(level: str) -> str:
        level = str(level).lower().strip()
        if level in {"high", "medium", "low"}:
            return level
        return "medium"

    def generate(
        self,
        on_line: Callable[[str], None] | None = None,
    ) -> ReportInsights:
        """Run the agent and return structured insights."""
        summary = self._load_summary()
        prompt = self._build_prompt(summary)
        result = self.adapter.run(prompt, cwd=self.project_dir, on_line=on_line)
        if not result.success:
            raise RuntimeError(f"AI report generation failed (exit {result.returncode})")

        data = self._parse_json_output(result.stdout)
        return self._to_insights(data)

    def _to_insights(self, data: dict) -> ReportInsights:
        key_changes = []
        for item in data.get("key_changes") or []:
            if not isinstance(item, dict):
                continue
            key_changes.append(
                KeyChange(
                    file=str(item.get("file", "")).strip(),
                    change_type=str(item.get("change_type", "other")).lower().strip() or "other",
                    complexity=self._normalize_level(item.get("complexity", "medium")),
                    risk_level=self._normalize_level(item.get("risk_level", "medium")),
                    description=str(item.get("description", "")).strip(),
                    review_suggestions=_to_string_list(item.get("review_suggestions")) or [],
                )
            )

        risks = []
        for item in data.get("risks") or []:
            if not isinstance(item, dict):
                continue
            risks.append(
                Risk(
                    level=self._normalize_level(item.get("level", "medium")),
                    description=str(item.get("description", "")).strip(),
                    files=_to_string_list(item.get("files")) or [],
                )
            )

        review_focus = []
        for item in data.get("review_focus") or []:
            if not isinstance(item, dict):
                continue
            review_focus.append(
                ReviewFocus(
                    priority=int(item.get("priority", 3)),
                    area=str(item.get("area", "")).strip(),
                    reason=str(item.get("reason", "")).strip(),
                )
            )
        review_focus.sort(key=lambda x: x.priority)

        next_actions = []
        for item in data.get("next_actions") or []:
            if not isinstance(item, dict):
                continue
            next_actions.append(
                NextAction(
                    action=str(item.get("action", "")).strip(),
                    urgency=str(item.get("urgency", "before_merge")).lower().strip() or "before_merge",
                )
            )

        return ReportInsights(
            summary=str(data.get("summary", "")).strip(),
            key_changes=key_changes,
            risks=risks,
            review_focus=review_focus,
            next_actions=next_actions,
        )


def _to_string_list(value: object | None) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]
