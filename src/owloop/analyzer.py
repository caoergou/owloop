"""Codebase analyzer for `owloop analyze`.

Scans a project directory for lint/type issues, code smells, and project health
metrics, then emits a structured Markdown or JSON report.
"""

from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# File-size / smell thresholds
LONG_FILE_LINES = 300
LONG_FUNCTION_LINES = 50


def _run_tool(command: list[str], cwd: Path, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    """Run a subprocess command and return its result."""
    return subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )


def _tool_on_path(name: str) -> bool:
    """Return True if the named executable is available on PATH."""
    return shutil.which(name) is not None


@dataclass
class ToolResult:
    """Result of running one external analysis tool."""

    name: str
    status: str  # e.g. "passed", "failed", "not configured", "not installed"
    output: str = ""


@dataclass
class SmellEntry:
    """A single code-smell finding."""

    category: str
    file: str
    detail: str


@dataclass
class AnalyzerReport:
    """Structured report produced by `Analyzer`."""

    generated_at: str
    project_dir: str
    total_files: int
    python_files: int
    test_files: int
    test_count: int | None
    issues_found: int
    lint_results: list[ToolResult] = field(default_factory=list)
    smells: list[SmellEntry] = field(default_factory=list)
    missing_docstrings: list[str] = field(default_factory=list)
    suggested_specs: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the report to a plain dictionary."""
        return {
            "generated_at": self.generated_at,
            "project_dir": self.project_dir,
            "total_files": self.total_files,
            "python_files": self.python_files,
            "test_files": self.test_files,
            "test_count": self.test_count,
            "issues_found": self.issues_found,
            "lint_results": [asdict(r) for r in self.lint_results],
            "smells": [asdict(s) for s in self.smells],
            "missing_docstrings": self.missing_docstrings,
            "suggested_specs": self.suggested_specs,
        }


class Analyzer:
    """Scan a Python project and produce a problem report."""

    IMPORT_RE: re.Pattern[str] = re.compile(
        r"^\s*(?:from\s+(\S+)\s+import\s+(.+)|import\s+(.+))$",
        re.MULTILINE,
    )
    TODO_RE: re.Pattern[str] = re.compile(r"#\s*(TODO|FIXME)\b", re.IGNORECASE)

    def __init__(self, project_dir: Path | str) -> None:
        self.project_dir = Path(project_dir)
        self.report = AnalyzerReport(
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            project_dir=str(self.project_dir.resolve()),
            total_files=0,
            python_files=0,
            test_files=0,
            test_count=None,
            issues_found=0,
        )

    def analyze(self) -> AnalyzerReport:
        """Run all analysis passes and return the populated report."""
        self._collect_file_stats()
        self._run_lint_tools()
        self._detect_code_smells()
        self._check_docstrings()
        self._build_spec_opportunities()
        self.report.issues_found = len(self.report.smells) + len(self.report.missing_docstrings)
        for tool in self.report.lint_results:
            if tool.status == "failed":
                self.report.issues_found += 1
        return self.report

    def _python_files(self) -> list[Path]:
        """Return all Python files under the project, excluding common hidden dirs."""
        files: list[Path] = []
        for path in self.project_dir.rglob("*.py"):
            rel = path.relative_to(self.project_dir)
            parts = rel.parts
            if any(p.startswith(".") for p in parts):
                continue
            if "__pycache__" in parts or "venv" in parts or ".venv" in parts:
                continue
            files.append(path)
        return files

    def _collect_file_stats(self) -> None:
        """Count total files, Python files, test files, and tests."""
        all_files = [
            p for p in self.project_dir.rglob("*")
            if p.is_file() and not any(part.startswith(".") for part in p.relative_to(self.project_dir).parts)
        ]
        self.report.total_files = len(all_files)
        py_files = self._python_files()
        self.report.python_files = len(py_files)
        self.report.test_files = sum(1 for p in py_files if "test" in p.name.lower())
        self.report.test_count = self._count_tests(py_files)

    def _count_tests(self, py_files: list[Path]) -> int | None:
        """Count test functions/classes if pytest is available."""
        if not _tool_on_path("pytest"):
            return None
        try:
            result = _run_tool(
                ["pytest", "--collect-only", "-q"],
                cwd=self.project_dir,
                timeout=30.0,
            )
        except (subprocess.TimeoutExpired, OSError):
            return None
        if result.returncode != 0:
            return None
        # The last non-empty line of quiet collection is typically "N tests collected".
        for line in reversed(result.stdout.splitlines()):
            line = line.strip()
            match = re.search(r"(\d+)\s+test", line)
            if match:
                return int(match.group(1))
        return None

    def _run_lint_tools(self) -> None:
        """Run ruff, mypy, and pytest collection when available/configured."""
        pyproject = self._read_pyproject()
        self._run_ruff(pyproject)
        self._run_mypy(pyproject)
        self._run_pytest_collect(pyproject)

    def _read_pyproject(self) -> dict[str, Any]:
        """Parse pyproject.toml if present, returning a dict of tool configs."""
        pyproject_path = self.project_dir / "pyproject.toml"
        if not pyproject_path.exists():
            return {}
        try:
            import tomllib  # Python 3.11+
        except ImportError:
            try:
                import tomli as tomllib  # type: ignore[import-not-found]
            except ImportError:
                return {}
        try:
            with pyproject_path.open("rb") as f:
                data = tomllib.load(f)
        except Exception:  # pragma: no cover - malformed pyproject
            return {}
        return data

    def _run_ruff(self, pyproject: dict[str, Any]) -> None:
        """Run `ruff check .` when configured or available."""
        configured = "tool" in pyproject and "ruff" in pyproject.get("tool", {})
        if not configured and not _tool_on_path("ruff"):
            self.report.lint_results.append(ToolResult("ruff", "not configured", ""))
            return
        if not _tool_on_path("ruff"):
            self.report.lint_results.append(ToolResult("ruff", "not installed", ""))
            return
        result = _run_tool(["ruff", "check", "."], cwd=self.project_dir, timeout=30.0)
        status = "passed" if result.returncode == 0 else "failed"
        output = result.stdout.strip() or result.stderr.strip() or ""
        self.report.lint_results.append(ToolResult("ruff", status, output))

    def _run_mypy(self, pyproject: dict[str, Any]) -> None:
        """Run mypy when configured in pyproject.toml or mypy.ini."""
        configured = "tool" in pyproject and "mypy" in pyproject.get("tool", {})
        if not configured and not (self.project_dir / "mypy.ini").exists():
            self.report.lint_results.append(ToolResult("mypy", "not configured", ""))
            return
        if not _tool_on_path("mypy"):
            self.report.lint_results.append(ToolResult("mypy", "not installed", ""))
            return
        result = _run_tool(["mypy", "."], cwd=self.project_dir, timeout=30.0)
        status = "passed" if result.returncode == 0 else "failed"
        output = result.stdout.strip() or result.stderr.strip() or ""
        self.report.lint_results.append(ToolResult("mypy", status, output))

    def _run_pytest_collect(self, pyproject: dict[str, Any]) -> None:
        """Run `pytest --collect-only` to detect collection/import errors."""
        if not _tool_on_path("pytest"):
            self.report.lint_results.append(ToolResult("pytest", "not installed", ""))
            return
        result = _run_tool(["pytest", "--collect-only", "-q"], cwd=self.project_dir, timeout=30.0)
        status = "passed" if result.returncode == 0 else "failed"
        output = result.stdout.strip() or result.stderr.strip() or ""
        self.report.lint_results.append(ToolResult("pytest", status, output))

    def _detect_code_smells(self) -> None:
        """Run lightweight heuristics for common code smells."""
        py_files = self._python_files()
        imports_by_file: dict[Path, set[str]] = {}
        all_definitions: dict[str, list[str]] = {}
        references: dict[str, int] = {}

        for path in py_files:
            rel = path.relative_to(self.project_dir).as_posix()
            content = path.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()

            self._check_long_file(path, rel, len(lines))
            self._check_long_functions(path, rel, content)
            self._check_todos(path, rel, content)

            imports = self._extract_imports(content)
            imports_by_file[path] = imports
            for imp in imports:
                references[imp] = references.get(imp, 0) + 1

            defs = self._extract_definitions(path, content)
            for name in defs:
                all_definitions.setdefault(name, []).append(rel)
                references[name] = references.get(name, 0)

        self._check_duplicate_imports(imports_by_file)
        self._check_dead_code(all_definitions, references)

    def _check_long_file(self, path: Path, rel: str, line_count: int) -> None:
        if line_count > LONG_FILE_LINES:
            self.report.smells.append(
                SmellEntry("Long files", rel, f"{line_count} lines")
            )

    def _check_long_functions(self, path: Path, rel: str, content: str) -> None:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                length = node.end_lineno - node.lineno + 1 if node.end_lineno else 0
                if length > LONG_FUNCTION_LINES:
                    self.report.smells.append(
                        SmellEntry(
                            "Long functions",
                            rel,
                            f"{node.name} ({length} lines)",
                        )
                    )

    def _check_todos(self, path: Path, rel: str, content: str) -> None:
        for lineno, line in enumerate(content.splitlines(), start=1):
            if self.TODO_RE.search(line):
                self.report.smells.append(
                    SmellEntry("TODO/FIXME comments", rel, f"line {lineno}")
                )

    def _extract_imports(self, content: str) -> set[str]:
        imports: set[str] = set()
        for match in self.IMPORT_RE.finditer(content):
            if match.group(1):
                module = match.group(1)
                names = [n.split()[0].strip() for n in match.group(2).split(",")]
                imports.update(f"{module}.{name}" for name in names)
            elif match.group(3):
                for token in match.group(3).split(","):
                    imports.add(token.split()[0].strip())
        return imports

    def _extract_definitions(self, path: Path, content: str) -> list[str]:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []
        defs: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not node.name.startswith("_"):
                # Ignore private/local definitions.
                defs.append(node.name)
        return defs

    def _check_duplicate_imports(self, imports_by_file: dict[Path, set[str]]) -> None:
        seen: dict[str, list[str]] = {}
        for path, imports in imports_by_file.items():
            rel = path.relative_to(self.project_dir).as_posix()
            for imp in imports:
                seen.setdefault(imp, []).append(rel)
        for imp, files in seen.items():
            if len(files) > 1:
                self.report.smells.append(
                    SmellEntry(
                        "Duplicate imports",
                        ", ".join(files),
                        f"{imp} imported in {len(files)} files",
                    )
                )

    def _check_dead_code(self, definitions: dict[str, list[str]], references: dict[str, int]) -> None:
        # Build a set of names that are defined and referenced outside their own file.
        # This is a heuristic: we count references from import lines and elsewhere.
        for name, files in definitions.items():
            # Skip dunder/main/dunder methods and obvious entry points.
            if name in {"main", "cli", "app"}:
                continue
            ref_count = references.get(name, 0)
            # A name referenced only by its own definitions file(s) is suspicious.
            if ref_count <= len(files):
                self.report.smells.append(
                    SmellEntry(
                        "Dead code hints",
                        ", ".join(files),
                        f"{name} may be unused",
                    )
                )

    def _check_docstrings(self) -> None:
        """Warn about public functions/classes missing docstrings."""
        for path in self._python_files():
            rel = path.relative_to(self.project_dir).as_posix()
            content = path.read_text(encoding="utf-8", errors="replace")
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if node.name.startswith("_"):
                        continue
                    if not ast.get_docstring(node):
                        self.report.missing_docstrings.append(f"{rel}:{node.name}")

    def _build_spec_opportunities(self) -> None:
        """Generate one-line spec titles from detected issue categories."""
        category_counts: dict[str, int] = {}
        category_examples: dict[str, str] = {}
        for smell in self.report.smells:
            category_counts[smell.category] = category_counts.get(smell.category, 0) + 1
            if smell.category not in category_examples:
                category_examples[smell.category] = smell.file

        for tool in self.report.lint_results:
            if tool.status == "failed":
                key = f"{tool.name} issues"
                category_counts[key] = 1
                category_examples[key] = tool.name

        if self.report.missing_docstrings:
            category_counts["Missing docstrings"] = len(self.report.missing_docstrings)
            category_examples["Missing docstrings"] = self.report.missing_docstrings[0]

        spec_map = {
            "Long files": "refactor-god-files",
            "Long functions": "split-long-functions",
            "TODO/FIXME comments": "resolve-todo-fixme-comments",
            "Duplicate imports": "deduplicate-imports",
            "Dead code hints": "remove-dead-code",
            "Missing docstrings": "add-missing-docstrings",
            "ruff issues": "fix-ruff-violations",
            "mypy issues": "fix-mypy-type-errors",
            "pytest issues": "fix-pytest-collection-errors",
        }

        for category, count in category_counts.items():
            slug = spec_map.get(category, "fix-" + category.lower().replace(" ", "-"))
            self.report.suggested_specs.append(
                {
                    "slug": slug,
                    "title": f"{slug} — address {category.lower()} ({count})",
                    "example": category_examples.get(category, ""),
                }
            )

    def to_markdown(self) -> str:
        """Render the analyzed report as Markdown."""
        r = self.report
        lines: list[str] = [
            "# owloop analysis report",
            "",
            f"Generated: {r.generated_at}",
            "",
            "## Summary",
            f"- Files: {r.total_files}",
            f"- Python files: {r.python_files}",
            f"- Tests: {r.test_count if r.test_count is not None else '—'}",
            f"- Issues found: {r.issues_found}",
            "",
            "## Lint / Type",
            "| Tool | Status | Output |",
            "|---|---|---|",
        ]
        for tool in r.lint_results:
            output = tool.output.replace("|", "\\|").replace("\n", " ") or "—"
            lines.append(f"| {tool.name} | {self._status_badge(tool.status)} | {output} |")

        lines.extend(["", "## Code Smells", "| Category | Count | Examples |", "|---|---|---|"])
        grouped: dict[str, list[str]] = {}
        for smell in r.smells:
            grouped.setdefault(smell.category, []).append(f"{smell.file}: {smell.detail}")

        if grouped:
            for category in sorted(grouped):
                examples = grouped[category]
                example_text = ", ".join(examples[:3])
                if len(examples) > 3:
                    example_text += f" (+{len(examples) - 3} more)"
                lines.append(f"| {category} | {len(examples)} | {example_text} |")
        else:
            lines.append("| — | 0 | — |")

        lines.extend(["", "## Suggested Specs"])
        if r.suggested_specs:
            for idx, spec in enumerate(r.suggested_specs, start=1):
                lines.append(f"{idx}. `{spec['slug']}` — {spec['title']}")
        else:
            lines.append("No issues detected — no specs suggested.")

        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _status_badge(status: str) -> str:
        if status == "passed":
            return "✅ passed"
        if status in {"not configured", "not installed"}:
            return "⚠️ " + status
        return "❌ " + status

    def write_report(self, output_path: Path | str, *, as_json: bool = False) -> Path:
        """Write the report to disk, creating parent directories if needed."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if as_json:
            path.write_text(json.dumps(self.report.to_dict(), indent=2), encoding="utf-8")
        else:
            path.write_text(self.to_markdown(), encoding="utf-8")
        return path


if __name__ == "__main__":  # pragma: no cover
    analyzer = Analyzer(Path.cwd())
    analyzer.analyze()
    print(analyzer.to_markdown())
