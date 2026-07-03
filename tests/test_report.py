"""Tests for the HTML report generator."""

import subprocess

from owloop.git_stats import CommitInfo, parse_git_stat
from owloop.report import ReportGenerator


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
