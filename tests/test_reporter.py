"""Tests for the plain-text ConsoleReporter."""

import re
import subprocess
from pathlib import Path

from rich.console import Console

from owloop.engine import RunSummary
from owloop.reporter import ConsoleReporter


def _make_repo_with_commits(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True, capture_output=True)

    (tmp_path / "a.txt").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "first commit"], cwd=tmp_path, check=True, capture_output=True)

    (tmp_path / "a.txt").write_text("hello world\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "second commit"], cwd=tmp_path, check=True, capture_output=True)

    return tmp_path


def _emoji_codepoints(text: str) -> list[str]:
    """Return characters that fall in common emoji Unicode ranges."""
    return [ch for ch in text if 0x1F300 <= ord(ch) <= 0x1F9FF or 0x2600 <= ord(ch) <= 0x26FF]


def test_session_info_outputs_mode_model_branch():
    console = Console(record=True)
    reporter = ConsoleReporter(console)
    reporter.on_event(
        "session_info",
        {
            "mode": "build",
            "model": "claude-sonnet",
            "branch": "feat/owl",
            "cwd": "/repo",
            "main_repo_dir": "/repo",
            "max_iterations": 5,
            "has_plan": False,
            "has_specs": True,
            "spec_count": 3,
            "incomplete_count": 2,
            "first_incomplete": "01-fix-ui.md",
        },
    )
    text = console.export_text()
    assert "build" in text
    assert "claude-sonnet" in text
    assert "feat/owl" in text
    assert "01-fix-ui.md" in text


def test_ascii_mode_avoids_emoji():
    console = Console(record=True)
    reporter = ConsoleReporter(console, ascii=True)
    reporter.on_event(
        "session_info",
        {
            "mode": "build",
            "model": "claude-sonnet",
            "branch": "feat/owl",
            "cwd": "/repo/.worktrees/feat-owl",
            "main_repo_dir": "/repo",
            "max_iterations": 5,
            "has_plan": False,
            "has_specs": True,
            "spec_count": 3,
            "incomplete_count": 2,
            "first_incomplete": "01-fix-ui.md",
        },
    )
    text = console.export_text()
    assert not _emoji_codepoints(text), f"found emoji in ascii output: {_emoji_codepoints(text)}"
    assert re.search(r"Mode:|Branch:|Model:", text)


def test_print_summary_shows_rich_stats(tmp_path):
    repo = _make_repo_with_commits(tmp_path)
    console = Console(record=True)
    reporter = ConsoleReporter(console)
    summary = RunSummary(
        iterations=2,
        branch="main",
        cwd=repo,
        main_repo_dir=repo,
        stopped_reason="max_iterations",
        tokens_used=1234,
    )
    reporter.print_summary(summary)
    text = console.export_text()

    assert "main" in text
    assert "2" in text
    assert "max_iterations" in text
    assert "first commit" in text
    assert "second commit" in text
    assert "1,234" in text
    assert "git log --oneline HEAD~2..HEAD" in text
    assert "git diff --stat HEAD~2..HEAD" in text


def test_print_summary_shows_token_warning_for_max_tokens(tmp_path):
    repo = _make_repo_with_commits(tmp_path)
    console = Console(record=True)
    reporter = ConsoleReporter(console)
    summary = RunSummary(
        iterations=1,
        branch="main",
        cwd=repo,
        main_repo_dir=repo,
        stopped_reason="max_tokens",
        tokens_used=9999,
    )
    reporter.print_summary(summary)
    text = console.export_text()

    assert "Token budget exhausted" in text


def test_print_summary_ascii_mode_avoids_emoji(tmp_path):
    repo = _make_repo_with_commits(tmp_path)
    console = Console(record=True)
    reporter = ConsoleReporter(console, ascii=True)
    summary = RunSummary(
        iterations=1,
        branch="main",
        cwd=repo,
        main_repo_dir=repo,
        stopped_reason="completed",
        tokens_used=0,
    )
    reporter.print_summary(summary)
    text = console.export_text()

    assert not _emoji_codepoints(text), f"found emoji in ascii output: {_emoji_codepoints(text)}"
    assert "main" in text
    assert "git log --oneline HEAD~1..HEAD" in text
