"""Tests for the owloop codebase analyzer."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from owloop.analyzer import Analyzer
from owloop.cli import main


def test_analyzer_counts_files(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# hello\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("def test_x(): pass\n", encoding="utf-8")

    analyzer = Analyzer(tmp_path)
    report = analyzer.analyze()

    assert report.total_files == 3
    assert report.python_files == 2
    assert report.test_files == 1


def test_detects_long_files(tmp_path: Path) -> None:
    (tmp_path / "long.py").write_text("# line\n" * 301, encoding="utf-8")
    analyzer = Analyzer(tmp_path)
    analyzer.analyze()
    assert any(s.category == "Long files" for s in analyzer.report.smells)


def test_detects_long_functions(tmp_path: Path) -> None:
    lines = ["def big():"] + ["    x = 1"] * 60
    (tmp_path / "funcs.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
    analyzer = Analyzer(tmp_path)
    analyzer.analyze()
    assert any(s.category == "Long functions" for s in analyzer.report.smells)


def test_detects_todo_comments(tmp_path: Path) -> None:
    (tmp_path / "todo.py").write_text("# TODO: fix this\n# FIXME: also this\n", encoding="utf-8")
    analyzer = Analyzer(tmp_path)
    analyzer.analyze()
    assert sum(1 for s in analyzer.report.smells if s.category == "TODO/FIXME comments") == 2


def test_detects_duplicate_imports(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("import os\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("import os\n", encoding="utf-8")
    analyzer = Analyzer(tmp_path)
    analyzer.analyze()
    assert any(s.category == "Duplicate imports" for s in analyzer.report.smells)


def test_detects_missing_docstrings(tmp_path: Path) -> None:
    (tmp_path / "nodoc.py").write_text("def public():\n    pass\n", encoding="utf-8")
    analyzer = Analyzer(tmp_path)
    analyzer.analyze()
    assert any("nodoc.py:public" in d for d in analyzer.report.missing_docstrings)


def test_markdown_report_contains_sections(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("# a module\n", encoding="utf-8")
    analyzer = Analyzer(tmp_path)
    analyzer.analyze()
    md = analyzer.to_markdown()
    assert "# owloop analysis report" in md
    assert "## Summary" in md
    assert "## Lint / Type" in md
    assert "## Code Smells" in md
    assert "## Suggested Specs" in md


def test_write_json_report(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    analyzer = Analyzer(tmp_path)
    analyzer.analyze()
    out = tmp_path / "out.json"
    analyzer.write_report(out, as_json=True)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["python_files"] == 1
    assert "lint_results" in data


def test_cli_analyze_default_output(tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as fs:
        Path(fs).joinpath("a.py").write_text("x = 1\n", encoding="utf-8")
        result = runner.invoke(main, ["analyze"])
        assert result.exit_code == 0, result.output
        assert (Path(fs) / "logs" / "owloop_analysis_latest.md").exists()
        assert "Analysis report written" in result.output


def test_cli_analyze_json_output(tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as fs:
        Path(fs).joinpath("a.py").write_text("x = 1\n", encoding="utf-8")
        result = runner.invoke(main, ["analyze", "--json"])
        assert result.exit_code == 0, result.output
        report = Path(fs) / "logs" / "owloop_analysis_latest.md"
        assert report.exists()
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["python_files"] == 1


def test_cli_analyze_custom_output(tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as fs:
        Path(fs).joinpath("a.py").write_text("x = 1\n", encoding="utf-8")
        custom = Path(fs) / "custom.md"
        result = runner.invoke(main, ["analyze", "-o", str(custom)])
        assert result.exit_code == 0, result.output
        assert custom.exists()
