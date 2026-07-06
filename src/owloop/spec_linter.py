"""Pre-flight spec linter for owloop.

`owloop check` uses `SpecLinter` to validate every spec in `specs/` before the
autonomous loop starts, surfacing structural errors, vague criteria, and
contradictions between Exclusions and Requirements/Acceptance Criteria.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from owloop import spec_queue
from owloop.backpressure import load_backpressure


@dataclass
class Finding:
    """A single lint message for a spec file."""

    severity: str  # "error" or "warning"
    message: str
    line: int | None = None

    def icon(self) -> str:
        return "✗" if self.severity == "error" else "⚠"


@dataclass
class LintReport:
    """Results of linting one or more specs."""

    results: dict[str, list[Finding]] = field(default_factory=dict)

    @property
    def spec_count(self) -> int:
        return len(self.results)

    @property
    def error_count(self) -> int:
        return sum(
            1 for findings in self.results.values() for finding in findings if finding.severity == "error"
        )

    @property
    def warning_count(self) -> int:
        return sum(
            1 for findings in self.results.values() for finding in findings if finding.severity == "warning"
        )


class SpecLinter:
    """Lint owloop markdown specs."""

    VAGUE_PHRASES: ClassVar[list[str]] = [
        "works correctly",
        "is clean",
        "properly",
        "should be",
        "make sure",
        "appropriate",
        "improve",
    ]

    _HEADER_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"^(##\s+)(.+?)\s*(?::\s*.*)?$",
        re.MULTILINE | re.IGNORECASE,
    )
    _CRITERION_RE: ClassVar[re.Pattern[str]] = re.compile(r"^\s*-\s*\[\s*\]\s+")
    _BACKTICK_RE: ClassVar[re.Pattern[str]] = re.compile(r"`[^`]+`")
    _DO_NOT_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"do\s+not\s+(modify|touch|change)\s+(.+)",
        re.IGNORECASE,
    )
    _BASELINE_CMD_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"^\s*-\s*\[\s*(.+?)\s*\]\s*:",
    )

    def __init__(self, specs_dir: Path | str, project_dir: Path | str | None = None) -> None:
        self.specs_dir = Path(specs_dir)
        if project_dir is not None:
            self.project_dir = Path(project_dir)
        else:
            self.project_dir = self.specs_dir.parent
        self._backpressure_commands = {
            cmd.command for cmd in load_backpressure(self.project_dir)
        }

    def lint_all(self, run_baseline: bool = False) -> LintReport:
        """Lint every ``*.md`` file in the specs directory."""
        report = LintReport()
        if not self.specs_dir.is_dir():
            return report

        for spec_file in sorted(self.specs_dir.glob("*.md")):
            report.results[spec_file.name] = self.lint_spec(spec_file, run_baseline=run_baseline)

        self._check_dependency_cycle(report)
        return report

    def _check_dependency_cycle(self, report: LintReport) -> None:
        """Flag every spec in a Depends On cycle with a clear error."""
        graph = spec_queue.build_dependency_graph(self.specs_dir)
        cycle = spec_queue.find_cycle(graph)
        if cycle is None:
            return

        chain = " -> ".join(spec.name for spec in cycle)
        message = f"circular spec dependency detected: {chain}"
        for spec in cycle[:-1]:
            report.results.setdefault(spec.name, []).append(Finding("error", message))

    def lint_spec(self, spec_file: Path, run_baseline: bool = False) -> list[Finding]:
        """Lint a single spec file and return all findings."""
        content = spec_file.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        sections, start_lines = self._parse_sections(content)
        findings: list[Finding] = []

        self._check_title(lines, findings)
        self._check_required_sections(sections, findings)
        self._check_criteria(sections, start_lines, findings)
        self._check_contradictions(sections, findings)
        self._check_warnings(lines, sections, findings)

        if run_baseline:
            self._run_baseline(sections, findings)

        return findings

    def _parse_sections(self, content: str) -> tuple[dict[str, list[str]], dict[str, int]]:
        """Return a mapping of section name -> body lines and header line numbers."""
        matches = list(self._HEADER_RE.finditer(content))
        sections: dict[str, list[str]] = {}
        start_lines: dict[str, int] = {}

        for index, match in enumerate(matches):
            name = match.group(2).strip().lower()
            body_start = match.end()
            body_end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
            body = content[body_start:body_end]
            body_lines = body.splitlines()
            # Drop the blank line that usually follows a markdown header.
            if body_lines and body_lines[0] == "":
                body_lines = body_lines[1:]
            sections[name] = body_lines
            start_lines[name] = content[: match.start()].count("\n") + 1

        return sections, start_lines

    @staticmethod
    def _section_has_content(body_lines: list[str]) -> bool:
        return any(re.search(r"\w", line) for line in body_lines)

    def _check_title(self, lines: list[str], findings: list[Finding]) -> None:
        first_non_empty = next((line for line in lines if line.strip()), "")
        if not first_non_empty.startswith("# "):
            findings.append(Finding("error", "missing top-level title"))

    def _check_required_sections(
        self, sections: dict[str, list[str]], findings: list[Finding]
    ) -> None:
        if "priority" not in sections:
            findings.append(Finding("error", "missing Priority section"))

        if "requirements" not in sections or not self._section_has_content(sections["requirements"]):
            findings.append(Finding("error", "Requirements section is empty"))

        if "acceptance criteria" not in sections or not self._section_has_content(
            sections["acceptance criteria"]
        ):
            findings.append(Finding("error", "Acceptance Criteria section is empty"))

        if "exclusions" not in sections or not self._section_has_content(sections["exclusions"]):
            findings.append(Finding("error", "Exclusions section is empty"))

    def _check_criteria(
        self,
        sections: dict[str, list[str]],
        start_lines: dict[str, int],
        findings: list[Finding],
    ) -> None:
        criteria = sections.get("acceptance criteria", [])
        if not criteria:
            return

        header_line = start_lines.get("acceptance criteria", 0)
        for offset, line in enumerate(criteria):
            if not self._CRITERION_RE.match(line):
                continue

            text = self._CRITERION_RE.sub("", line).strip()
            lowered = text.lower()
            for phrase in self.VAGUE_PHRASES:
                if phrase.lower() in lowered:
                    findings.append(
                        Finding("error", f'acceptance criterion is vague: "{text}"')
                    )
                    break

            if not self._BACKTICK_RE.search(line):
                line_number = header_line + 1 + offset
                findings.append(Finding("error", f"no shell command in criterion: line {line_number}"))
                continue

            if self._backpressure_commands:
                backtick = self._BACKTICK_RE.search(line)
                command = backtick.group(0).strip("`") if backtick else ""
                # Allow commands that start with a known backpressure command.
                if command and not any(
                    command == known or command.startswith(known + " ")
                    for known in self._backpressure_commands
                ):
                    findings.append(
                        Finding(
                            "warning",
                            f"criterion command is not in discovered backpressure commands: {command}",
                        )
                    )

    def _check_contradictions(
        self, sections: dict[str, list[str]], findings: list[Finding]
    ) -> None:
        exclusions = sections.get("exclusions", [])
        if not exclusions:
            return

        targets: set[str] = set()
        for line in exclusions:
            for match in self._DO_NOT_RE.finditer(line):
                rest = match.group(2).strip().rstrip(".!")
                for raw_token in re.split(r",|\bor\b", rest):
                    token = raw_token.strip().strip("[]")
                    if token and re.search(r"\w", token):
                        targets.add(token)

        if not targets:
            return

        req_text = "\n".join(sections.get("requirements", []))
        ac_text = "\n".join(sections.get("acceptance criteria", []))

        for target in targets:
            if target in req_text or target in ac_text:
                findings.append(
                    Finding(
                        "error",
                        f"contradiction: Exclusions prohibits modifying {target}, "
                        "but it is mentioned in Requirements or Acceptance Criteria",
                    )
                )

    def _check_warnings(
        self,
        lines: list[str],
        sections: dict[str, list[str]],
        findings: list[Finding],
    ) -> None:
        if "verification" not in sections:
            findings.append(Finding("warning", "missing Verification section"))
        if "baseline" not in sections:
            findings.append(Finding("warning", "missing Baseline section"))
        if not self._has_done_promise(lines):
            findings.append(
                Finding("warning", "missing <promise>DONE</promise> in last 3 lines")
            )

    @staticmethod
    def _has_done_promise(lines: list[str]) -> bool:
        tail = [line.strip() for line in lines[-3:] if line.strip()]
        return any(line == "<promise>DONE</promise>" for line in tail)

    def _run_baseline(self, sections: dict[str, list[str]], findings: list[Finding]) -> None:
        baseline = sections.get("baseline", [])
        for line in baseline:
            match = self._BASELINE_CMD_RE.match(line)
            if not match:
                continue
            command = match.group(1).strip()
            try:
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            except subprocess.TimeoutExpired:
                findings.append(Finding("error", f"baseline command timed out: {command}"))
                continue

            if result.returncode != 0:
                stderr = result.stderr.strip().replace("\n", " ")[:80]
                findings.append(
                    Finding(
                        "error",
                        f"baseline command failed ({result.returncode}): {command} — {stderr}",
                    )
                )
