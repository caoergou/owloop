"""Spec quality review — static, executable, and agent-driven checks.

A spec review runs after generation and before execution. It catches common
spec defects (vague criteria, missing commands, scope creep) so the loop does
not waste tokens on impossible tasks.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from owloop.adapters import AgentAdapter
from owloop.spec_linter import Finding, SpecLinter


@dataclass
class ReviewReport:
    """Results of reviewing one or more specs."""

    spec_file: Path
    findings: list[Finding] = field(default_factory=list)
    auto_fixed: list[str] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warning")


class SpecReview:
    """Run static, executable, and optional agent review on a spec."""

    AGENT_REVIEW_PROMPT = """\
# Owloop — Spec Quality Review

You are reviewing an owloop spec before it is executed by an autonomous agent.
Identify concrete problems. Do NOT rewrite the spec.

Check for:
- Unrealistic targets (e.g., "100% coverage" without a plan).
- Vague exclusions (e.g., "don't break things").
- Scope creep (touches 10+ files or multiple unrelated subsystems).
- Missing edge cases or error handling.
- Conflicts between Requirements and Exclusions.

Output a concise bulleted list. Start each bullet with `[ERROR]` or `[WARNING]`.
If the spec looks good, output `<promise>PASS</promise>`.
"""

    def __init__(
        self,
        specs_dir: Path,
        project_dir: Path | None = None,
        adapter: AgentAdapter | None = None,
    ) -> None:
        self.specs_dir = Path(specs_dir)
        self.project_dir = Path(project_dir) if project_dir else self.specs_dir.parent
        self.adapter = adapter

    def review(self, spec_file: Path, *, auto_fix: bool = True) -> ReviewReport:
        """Run all review stages on a single spec."""
        report = ReviewReport(spec_file=spec_file)

        self._static_check(spec_file, report)
        self._executable_check(spec_file, report)

        if auto_fix:
            self._auto_fix(spec_file, report)

        if self.adapter is not None:
            self._agent_review(spec_file, report)

        return report

    def _static_check(self, spec_file: Path, report: ReviewReport) -> None:
        linter = SpecLinter(self.specs_dir, project_dir=self.project_dir)
        findings = linter.lint_spec(spec_file)
        report.findings.extend(findings)

    def _executable_check(self, spec_file: Path, report: ReviewReport) -> None:
        content = spec_file.read_text(encoding="utf-8")
        in_criteria = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("## acceptance criteria"):
                in_criteria = True
                continue
            if stripped.startswith("## ") and "acceptance" not in stripped.lower():
                in_criteria = False
                continue
            if not in_criteria:
                continue

            backtick = self._extract_backtick_command(stripped)
            if not backtick:
                continue

            first = backtick.split()[0]
            if shutil.which(first) is None:
                report.findings.append(
                    Finding(
                        "error",
                        f"acceptance criterion command not found on PATH: {first}",
                    )
                )

    @staticmethod
    def _extract_backtick_command(line: str) -> str:
        if "`" not in line:
            return ""
        parts = line.split("`")
        if len(parts) < 3:
            return ""
        return parts[1].strip()

    def _auto_fix(self, spec_file: Path, report: ReviewReport) -> None:
        content = spec_file.read_text(encoding="utf-8")
        original = content

        # Fix: ensure a Verification section exists.
        if "## Verification" not in content:
            content += "\n## Verification\nRun the acceptance criteria commands after each change.\n"
            report.auto_fixed.append("added missing Verification section")

        # Fix: ensure the spec ends with a DONE promise.
        if "<promise>DONE</promise>" not in content:
            content += "\nOutput when complete: `<promise>DONE</promise>`\n"
            report.auto_fixed.append("added missing <promise>DONE</promise>")

        if content != original:
            spec_file.write_text(content, encoding="utf-8")

    def _agent_review(self, spec_file: Path, report: ReviewReport) -> None:
        prompt = (
            f"{self.AGENT_REVIEW_PROMPT}\n\n---\n\n"
            f"Spec file: {spec_file.name}\n\n"
            f"{spec_file.read_text(encoding='utf-8')}"
        )
        adapter = self.adapter
        assert adapter is not None
        result = adapter.run(prompt, cwd=self.project_dir)

        if "<promise>PASS</promise>" in result.stdout:
            return

        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("[ERROR]"):
                report.findings.append(
                    Finding("error", stripped.removeprefix("[ERROR]").strip())
                )
            elif stripped.startswith("[WARNING]"):
                report.findings.append(
                    Finding("warning", stripped.removeprefix("[WARNING]").strip())
                )
