"""Tests for AI-generated report insights."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from owloop.adapters import AgentResult, MockAdapter
from owloop.report_ai import AIReportInsightsGenerator


def _git_init(repo: Path) -> None:
    """Initialize a git repo with an initial commit so HEAD exists."""
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("# test", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)


def _write_summary(repo: Path, iterations: int = 1, stopped_reason: str = "completed") -> None:
    summary_dir = repo / ".owloop" / "logs"
    summary_dir.mkdir(parents=True)
    summary = {
        "iterations": iterations,
        "branch": "main",
        "stopped_reason": stopped_reason,
        "tokens_used": 12345,
    }
    (summary_dir / "owloop_summary_latest.json").write_text(
        json.dumps(summary), encoding="utf-8"
    )


def _sample_ai_response() -> str:
    return json.dumps({
        "summary": "Run completed two small refactors.",
        "key_changes": [
            {
                "file": "src/core.py",
                "change_type": "refactor",
                "complexity": "medium",
                "risk_level": "medium",
                "description": "Extracted helper function.",
                "review_suggestions": ["Check edge cases"],
            }
        ],
        "risks": [
            {
                "level": "medium",
                "description": "Helper may change exception handling.",
                "files": ["src/core.py"],
            }
        ],
        "review_focus": [
            {"priority": 1, "area": "Exception paths", "reason": "Behavior could shift."}
        ],
        "next_actions": [
            {"action": "Run pytest src/core.py", "urgency": "now"}
        ],
    })


def test_generate_parses_structured_output(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _write_summary(repo)
    (repo / ".owloop" / "specs").mkdir(parents=True)
    (repo / ".owloop" / "specs" / "01-test.md").write_text("# Spec\n", encoding="utf-8")

    adapter = MockAdapter(responses=[
        AgentResult(
            stdout=_sample_ai_response(),
            returncode=0,
            success=True,
            has_completion_signal=False,
        )
    ])
    generator = AIReportInsightsGenerator(repo, adapter)
    insights = generator.generate()

    assert "Run completed" in insights.summary
    assert len(insights.key_changes) == 1
    assert insights.key_changes[0].file == "src/core.py"
    assert insights.key_changes[0].complexity == "medium"
    assert len(insights.risks) == 1
    assert insights.risks[0].files == ["src/core.py"]
    assert len(insights.review_focus) == 1
    assert insights.review_focus[0].priority == 1
    assert len(insights.next_actions) == 1
    assert insights.next_actions[0].urgency == "now"


def test_generate_raises_on_missing_summary(tmp_path: Path) -> None:
    adapter = MockAdapter()
    generator = AIReportInsightsGenerator(tmp_path, adapter)

    with pytest.raises(FileNotFoundError):
        generator.generate()


def test_generate_raises_on_invalid_json(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _write_summary(repo)

    adapter = MockAdapter(responses=[
        AgentResult(
            stdout="not json",
            returncode=0,
            success=True,
            has_completion_signal=False,
        )
    ])
    generator = AIReportInsightsGenerator(repo, adapter)

    with pytest.raises(ValueError):
        generator.generate()


def test_generate_prompt_includes_guidelines(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _write_summary(repo)

    adapter = MockAdapter(responses=[
        AgentResult(
            stdout=_sample_ai_response(),
            returncode=0,
            success=True,
            has_completion_signal=False,
        )
    ])
    generator = AIReportInsightsGenerator(repo, adapter)
    generator.generate()

    prompt, _cwd = adapter.calls[0]
    assert "complexity" in prompt
    assert "risk_level" in prompt
    assert "key_changes" in prompt
    assert "Do not summarize everything" in prompt
    assert "focus on what actually matters" in prompt


def test_generate_orders_review_focus_by_priority(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _write_summary(repo)

    response = {
        "summary": "Test",
        "key_changes": [],
        "risks": [],
        "review_focus": [
            {"priority": 3, "area": "Later", "reason": "r3"},
            {"priority": 1, "area": "First", "reason": "r1"},
            {"priority": 2, "area": "Middle", "reason": "r2"},
        ],
        "next_actions": [],
    }
    adapter = MockAdapter(responses=[
        AgentResult(
            stdout=json.dumps(response),
            returncode=0,
            success=True,
            has_completion_signal=False,
        )
    ])
    generator = AIReportInsightsGenerator(repo, adapter)
    insights = generator.generate()

    areas = [item.area for item in insights.review_focus]
    assert areas == ["First", "Middle", "Later"]
