"""Tests for spec generation from GitHub issues."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from owloop.cli import main
from owloop.spec_from_issue import IssueToSpecConverter

SAMPLE_GH_OUTPUT = json.dumps(
    {
        "number": 42,
        "title": "Add dark mode",
        "state": "open",
        "body": (
            "We need a dark mode toggle.\n\n"
            "- [ ] Add toggle UI\n"
            "- [x] Persist user preference\n"
            "- [ ] Update CSS variables"
        ),
    }
)


TEMPLATE_CONTENT = (
    "# Feature: [name]\n\n## Priority: [1-5]\n\n## Requirements\n[placeholder]\n\n"
    "## Acceptance Criteria\n[placeholder]\n\n## Exclusions\n- Do not modify unrelated files\n"
)


def _write_template(project_dir: Path) -> None:
    """Write a minimal spec template for testing."""
    from owloop.paths import resolve_templates_dir
    template_path = resolve_templates_dir(project_dir) / "spec-template.md"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(TEMPLATE_CONTENT, encoding="utf-8")


def _make_converter(tmp_path: Path) -> IssueToSpecConverter:
    """Create a converter with a populated spec template."""
    _write_template(tmp_path)
    return IssueToSpecConverter(tmp_path)


def test_parse_full_issue_url():
    converter = IssueToSpecConverter(Path.cwd())
    owner, repo, number = converter._parse_issue(
        "https://github.com/acme/corp/issues/123"
    )
    assert owner == "acme"
    assert repo == "corp"
    assert number == 123


def test_parse_issue_url_with_query_string():
    converter = IssueToSpecConverter(Path.cwd())
    owner, repo, number = converter._parse_issue(
        "https://github.com/acme/corp/issues/123?foo=bar"
    )
    assert number == 123


def test_parse_issue_number_with_repo():
    converter = IssueToSpecConverter(Path.cwd())
    owner, repo, number = converter._parse_issue("456", repo="acme/corp")
    assert owner == "acme"
    assert repo == "corp"
    assert number == 456


def test_parse_issue_number_requires_repo(tmp_path: Path):
    converter = IssueToSpecConverter(tmp_path)
    with pytest.raises(ValueError, match="Could not determine"):
        converter._parse_issue("456")


def test_parse_invalid_issue_reference():
    converter = IssueToSpecConverter(Path.cwd())
    with pytest.raises(ValueError, match="Invalid issue reference"):
        converter._parse_issue("not-a-url-or-number")


def test_infer_repo_from_https_remote(tmp_path: Path):
    def fake_run(cmd: list[str], **kwargs: Any) -> MagicMock:
        result = MagicMock()
        result.stdout = "https://github.com/acme/corp.git\n"
        result.stderr = ""
        result.returncode = 0
        return result

    converter = IssueToSpecConverter(tmp_path)
    with patch("subprocess.run", side_effect=fake_run):
        assert converter._infer_repo() == "acme/corp"


def test_infer_repo_from_ssh_remote(tmp_path: Path):
    def fake_run(cmd: list[str], **kwargs: Any) -> MagicMock:
        result = MagicMock()
        result.stdout = "git@github.com:acme/corp.git\n"
        result.stderr = ""
        result.returncode = 0
        return result

    converter = IssueToSpecConverter(tmp_path)
    with patch("subprocess.run", side_effect=fake_run):
        assert converter._infer_repo() == "acme/corp"


def test_infer_repo_when_no_git_remote(tmp_path: Path):
    converter = IssueToSpecConverter(tmp_path)
    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "git")):
        assert converter._infer_repo() is None


def test_fetch_with_gh_success(tmp_path: Path):
    converter = IssueToSpecConverter(tmp_path)

    def fake_run(cmd: list[str], **kwargs: Any) -> MagicMock:
        assert cmd[0] == "gh"
        result = MagicMock()
        result.stdout = SAMPLE_GH_OUTPUT
        result.stderr = ""
        result.returncode = 0
        return result

    with (
        patch("shutil.which", return_value="/usr/bin/gh"),
        patch("subprocess.run", side_effect=fake_run),
    ):
        data = converter._fetch_issue("acme", "corp", 42)

    assert data["number"] == 42
    assert data["title"] == "Add dark mode"


def test_fetch_with_gh_not_found(tmp_path: Path):
    converter = IssueToSpecConverter(tmp_path)

    def fake_run(cmd: list[str], **kwargs: Any) -> MagicMock:
        result = MagicMock()
        result.stdout = ""
        result.stderr = "HTTP 404: Not Found"
        result.returncode = 1
        raise subprocess.CalledProcessError(1, cmd, output=result.stdout, stderr=result.stderr)

    with (
        patch("shutil.which", return_value="/usr/bin/gh"),
        patch("subprocess.run", side_effect=fake_run),
        pytest.raises(RuntimeError, match="not found"),
    ):
        converter._fetch_issue("acme", "corp", 42)


def test_fetch_falls_back_to_requests(tmp_path: Path):
    converter = IssueToSpecConverter(tmp_path)

    response = MagicMock()
    response.status_code = 200
    response.json.return_value = json.loads(SAMPLE_GH_OUTPUT)
    response.text = SAMPLE_GH_OUTPUT

    with (
        patch("shutil.which", return_value=None),
        patch(
            "owloop.spec_from_issue.IssueToSpecConverter._fetch_with_requests",
            return_value=json.loads(SAMPLE_GH_OUTPUT),
        ) as mock_requests,
    ):
        data = converter._fetch_issue("acme", "corp", 42)

    mock_requests.assert_called_once_with("acme", "corp", 42)
    assert data["title"] == "Add dark mode"


def test_parse_issue_body_splits_checklists():
    converter = IssueToSpecConverter(Path.cwd())
    body = (
        "We need a dark mode toggle.\n\n"
        "- [ ] Add toggle UI\n"
        "- [x] Persist user preference\n"
        "- [ ] Update CSS variables"
    )
    requirements, criteria = converter._parse_issue_body(body)
    assert "dark mode toggle" in requirements
    assert "Add toggle UI" not in requirements
    assert "- [ ] Add toggle UI" in criteria
    assert "- [ ] Persist user preference" in criteria
    assert "- [ ] Update CSS variables" in criteria


def test_render_spec_from_mocked_data(tmp_path: Path):
    converter = _make_converter(tmp_path)
    data = {
        "title": "Add dark mode",
        "number": "42",
        "state": "open",
        "body": "We need a dark mode toggle.",
        "requirements": "We need a dark mode toggle.",
        "acceptance_criteria": "- [ ] Add toggle UI",
    }
    rendered = converter.render_spec(data)
    assert "# Feature: Add dark mode" in rendered
    assert "## Priority: 3" in rendered
    assert "We need a dark mode toggle." in rendered
    assert "- [ ] Add toggle UI" in rendered


def test_next_spec_number_empty_directory(tmp_path: Path):
    converter = _make_converter(tmp_path)
    assert converter._next_spec_number() == 1


def test_next_spec_number_finds_gap(tmp_path: Path):
    converter = _make_converter(tmp_path)
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    (specs_dir / "001-first.md").write_text("x", encoding="utf-8")
    (specs_dir / "003-third.md").write_text("x", encoding="utf-8")
    assert converter._next_spec_number() == 4


def test_write_spec_creates_numbered_file(tmp_path: Path):
    converter = _make_converter(tmp_path)
    data = {
        "title": "Add dark mode",
        "number": "42",
        "state": "open",
        "body": "Body",
        "requirements": "Req",
        "acceptance_criteria": "- [ ] Criterion",
    }
    path = converter.write_spec(data)
    assert path.name == "001-add-dark-mode.md"
    assert path.exists()


def test_write_spec_with_output_override(tmp_path: Path):
    converter = _make_converter(tmp_path)
    data = {
        "title": "Add dark mode",
        "number": "42",
        "state": "open",
        "body": "Body",
        "requirements": "Req",
        "acceptance_criteria": "- [ ] Criterion",
    }
    override = tmp_path / "custom.md"
    path = converter.write_spec(data, output_path=override)
    assert path == override
    assert path.exists()


def test_slugify_truncates_and_cleans():
    converter = IssueToSpecConverter(Path.cwd())
    assert converter._slugify("Hello World!") == "hello-world"
    assert len(converter._slugify("a " * 100)) <= 50


def test_cli_spec_from_issue_dry_run(monkeypatch: pytest.MonkeyPatch):
    runner = CliRunner()

    def fake_from_github(issue: str, repo: str | None = None) -> dict[str, str]:
        return {
            "title": "Add dark mode",
            "number": "42",
            "state": "open",
            "body": "Body",
            "requirements": "Req",
            "acceptance_criteria": "- [ ] Criterion",
        }

    monkeypatch.setattr(
        IssueToSpecConverter, "from_github", staticmethod(lambda issue, repo=None: fake_from_github(issue, repo))
    )

    with runner.isolated_filesystem() as fs:
        project_dir = Path(fs)
        subprocess.run(["git", "init"], cwd=project_dir, check=True, capture_output=True)
        (project_dir / ".owloop").mkdir(parents=True)
        _write_template(project_dir)
        result = runner.invoke(main, ["spec-from-issue", "--dry-run", "42", "--repo", "acme/corp"])

    assert result.exit_code == 0, result.output
    assert "Add dark mode" in result.output


def test_cli_spec_from_issue_writes_spec(monkeypatch: pytest.MonkeyPatch):
    runner = CliRunner()

    def fake_from_github(issue: str, repo: str | None = None) -> dict[str, str]:
        return {
            "title": "Add dark mode",
            "number": "42",
            "state": "open",
            "body": "Body",
            "requirements": "Req",
            "acceptance_criteria": "- [ ] Criterion",
        }

    monkeypatch.setattr(
        IssueToSpecConverter, "from_github", staticmethod(lambda issue, repo=None: fake_from_github(issue, repo))
    )

    with runner.isolated_filesystem() as fs:
        project_dir = Path(fs)
        subprocess.run(["git", "init"], cwd=project_dir, check=True, capture_output=True)
        (project_dir / ".owloop").mkdir(parents=True)
        _write_template(project_dir)
        result = runner.invoke(main, ["spec-from-issue", "42", "--repo", "acme/corp"])
        assert result.exit_code == 0, result.output
        assert "Spec generated" in result.output
        assert (project_dir / ".owloop" / "specs" / "001-add-dark-mode.md").exists()


def test_cli_spec_from_issue_missing_repo():
    runner = CliRunner()
    with runner.isolated_filesystem() as fs:
        project_dir = Path(fs)
        subprocess.run(["git", "init"], cwd=project_dir, check=True, capture_output=True)
        result = runner.invoke(main, ["spec-from-issue", "42"])
    assert result.exit_code == 1
    assert "Could not determine" in result.output


def test_cli_spec_from_issue_missing_template(monkeypatch: pytest.MonkeyPatch):
    runner = CliRunner()

    def fake_from_github(issue: str, repo: str | None = None) -> dict[str, str]:
        return {
            "title": "Add dark mode",
            "number": "42",
            "state": "open",
            "body": "Body",
            "requirements": "Req",
            "acceptance_criteria": "- [ ] Criterion",
        }

    monkeypatch.setattr(
        IssueToSpecConverter, "from_github", staticmethod(lambda issue, repo=None: fake_from_github(issue, repo))
    )

    with runner.isolated_filesystem() as fs:
        project_dir = Path(fs)
        subprocess.run(["git", "init"], cwd=project_dir, check=True, capture_output=True)
        result = runner.invoke(main, ["spec-from-issue", "42", "--repo", "acme/corp"])

    assert result.exit_code == 1
    assert "Spec template not found" in result.output
