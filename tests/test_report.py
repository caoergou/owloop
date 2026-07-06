"""Tests for the HTML report generator."""

import subprocess

from owloop.git_stats import CommitInfo, parse_git_stat
from owloop.report import ReportGenerator
from owloop.report_ai import (
    KeyChange,
    NextAction,
    ReportInsights,
    ReviewFocus,
    Risk,
)


def _make_repo_with_commits(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True, capture_output=True)

    (tmp_path / "a.txt").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "first commit"], cwd=tmp_path, check=True, capture_output=True)

    (tmp_path / "a.txt").write_text("hello world\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "second commit"], cwd=tmp_path, check=True, capture_output=True)

    return tmp_path


def test_parse_stat_extracts_counts():
    stat = " file.txt | 5 +++++\n 1 file changed, 5 insertions(+), 0 deletions(-)"
    files, ins, dels = parse_git_stat(stat)
    assert files == 1
    assert ins == 5
    assert dels == 0


def test_generate_report_from_summary(tmp_path):
    repo = _make_repo_with_commits(tmp_path)
    logs_dir = repo / "logs"
    logs_dir.mkdir()
    summary = {
        "branch": "main",
        "iterations": 2,
        "cwd": str(repo),
        "main_repo_dir": str(repo),
        "stopped_reason": "max_iterations",
        "issues": None,
        "tokens_used": 1234,
    }
    (logs_dir / "owloop_summary_latest.json").write_text(__import__("json").dumps(summary), encoding="utf-8")

    generator = ReportGenerator(repo)
    report_path = generator.generate()

    assert report_path.exists()
    html = report_path.read_text(encoding="utf-8")
    assert "owloop report" in html
    assert "main" in html
    assert "first commit" in html
    assert "second commit" in html
    assert "1,234" in html


def test_commit_info_dataclass():
    commit = CommitInfo(hash="abc123", message="feat: x", author="Ollie", date="now")
    assert commit.files_changed == 0


def test_report_includes_review_commands_and_branch_diff(tmp_path):
    repo = _make_repo_with_commits(tmp_path)
    logs_dir = repo / "logs"
    logs_dir.mkdir()
    summary = {
        "branch": "main",
        "iterations": 2,
        "cwd": str(repo),
        "main_repo_dir": str(repo),
        "stopped_reason": "max_iterations",
        "issues": None,
        "tokens_used": 1234,
    }
    (logs_dir / "owloop_summary_latest.json").write_text(__import__("json").dumps(summary), encoding="utf-8")

    generator = ReportGenerator(repo)
    report_path = generator.generate()
    html = report_path.read_text(encoding="utf-8")

    assert "git log --oneline HEAD~2..HEAD" in html
    assert "git diff --stat HEAD~2..HEAD" in html
    assert "Branch diff" in html
    assert "files" in html


def test_report_renders_ai_insights(tmp_path):
    repo = _make_repo_with_commits(tmp_path)
    logs_dir = repo / "logs"
    logs_dir.mkdir()
    summary = {
        "branch": "main",
        "iterations": 2,
        "cwd": str(repo),
        "main_repo_dir": str(repo),
        "stopped_reason": "max_iterations",
        "issues": None,
        "tokens_used": 1234,
    }
    (logs_dir / "owloop_summary_latest.json").write_text(__import__("json").dumps(summary), encoding="utf-8")

    insights = ReportInsights(
        summary="Two small changes.",
        key_changes=[
            KeyChange(
                file="src/core.py",
                change_type="refactor",
                complexity="medium",
                risk_level="medium",
                description="Extracted helper.",
                review_suggestions=["Check edge cases"],
            )
        ],
        risks=[Risk(level="medium", description="Behavior may shift.", files=["src/core.py"])],
        review_focus=[ReviewFocus(priority=1, area="Exception paths", reason="Behavior could shift.")],
        next_actions=[NextAction(action="Run pytest", urgency="now")],
    )

    generator = ReportGenerator(repo)
    report_path = generator.generate(insights=insights)
    html = report_path.read_text(encoding="utf-8")

    assert "AI Review Insights" in html
    assert "src/core.py" in html
    assert "Key Changes" in html
    assert "Risks" in html
    assert "Review Focus" in html
    assert "Next Actions" in html
    assert "Run pytest" in html


def test_report_includes_event_timeline(tmp_path):
    repo = _make_repo_with_commits(tmp_path)
    logs_dir = repo / "logs"
    logs_dir.mkdir()
    summary = {
        "branch": "main",
        "iterations": 2,
        "cwd": str(repo),
        "main_repo_dir": str(repo),
        "stopped_reason": "blocked",
        "issues": None,
        "tokens_used": 1234,
    }
    (logs_dir / "owloop_summary_latest.json").write_text(__import__("json").dumps(summary), encoding="utf-8")

    events = [
        {"ts": "2026-07-06T10:00:00", "session_id": "sess1", "kind": "iteration_start", "data": {"iteration": 1}},
        {"ts": "2026-07-06T10:01:00", "session_id": "sess1", "kind": "iteration_end", "data": {"iteration": 1, "success": True}},
        {"ts": "2026-07-06T10:02:00", "session_id": "sess1", "kind": "blocked", "data": {"payload": "missing API key"}},
    ]
    events_text = "\n".join(__import__("json").dumps(e) for e in events)
    (logs_dir / "events.jsonl").write_text(events_text, encoding="utf-8")

    generator = ReportGenerator(repo)
    report_path = generator.generate()
    html = report_path.read_text(encoding="utf-8")

    assert "Event Timeline" in html
    assert "iteration_start" in html
    assert "iteration_end" in html
    assert "Failure Reasons" in html
    assert "missing API key" in html
