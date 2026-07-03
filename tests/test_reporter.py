"""Tests for the plain-text ConsoleReporter."""

import re

from rich.console import Console

from owloop.reporter import ConsoleReporter


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
