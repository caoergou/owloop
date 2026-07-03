"""Tests for the owloop CLI entry points."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version

import pytest
from click.testing import CliRunner

from owloop.cli import main, parse_max_tokens


def _installed_version() -> str:
    try:
        return pkg_version("owloop")
    except PackageNotFoundError:  # pragma: no cover - fallback for editable runs
        return "0.0.0"


def test_banner_and_command_list():
    runner = CliRunner()
    result = runner.invoke(main)
    assert result.exit_code == 0
    assert "owloop" in result.output
    assert "owloop init" in result.output
    assert "owloop run" in result.output
    assert "owloop status" in result.output
    assert "owloop version" in result.output


def test_version_flag():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert _installed_version() in result.output


def test_version_command():
    runner = CliRunner()
    result = runner.invoke(main, ["version"])
    assert result.exit_code == 0
    assert "owloop" in result.output


def test_init_help():
    runner = CliRunner()
    result = runner.invoke(main, ["init", "--help"])
    assert result.exit_code == 0
    assert "Initialize owloop" in result.output


def test_status_without_specs_dir():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["status"])
        assert result.exit_code == 1
        assert "No specs directory" in result.output


def test_run_without_specs_dir():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["run"])
        assert result.exit_code == 1
        assert "No specs found" in result.output


def test_init_requires_git_repo():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["init"])
        assert result.exit_code == 1
        assert "Not a git repository" in result.output


def test_init_creates_dot_owloop_dir():
    runner = CliRunner()
    with runner.isolated_filesystem():
        import subprocess
        subprocess.run(["git", "init"], check=True, capture_output=True)
        result = runner.invoke(main, ["init"])
        assert result.exit_code == 0
        from pathlib import Path
        assert (Path.cwd() / ".owloop").is_dir()
        assert (Path.cwd() / ".owloop" / "specs").is_dir()
        assert (Path.cwd() / ".owloop" / "logs").is_dir()
        assert (Path.cwd() / ".owloop" / "specs" / "01-example.md").is_file()


def test_spec_help():
    runner = CliRunner()
    result = runner.invoke(main, ["spec", "--help"])
    assert result.exit_code == 0
    assert "Turn a vague goal" in result.output


def test_spec_requires_git_repo():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["spec", "refactor error handling"])
        assert result.exit_code == 1
        assert "Not a git repository" in result.output


def test_report_no_ai_skips_adapter():
    runner = CliRunner()
    with runner.isolated_filesystem():
        import subprocess
        from pathlib import Path
        subprocess.run(["git", "init"], check=True, capture_output=True)
        Path(".owloop/logs").mkdir(parents=True)
        Path(".owloop/logs/owloop_summary_latest.json").write_text(
            '{"iterations": 0, "branch": "main", "stopped_reason": "completed"}',
            encoding="utf-8",
        )
        result = runner.invoke(main, ["report", "--no-ai"])
        assert result.exit_code == 0
        assert "Report generated" in result.output


def test_parse_max_tokens_plain_number():
    assert parse_max_tokens("12345") == 12345


def test_parse_max_tokens_shorthand():
    assert parse_max_tokens("10k") == 10_000
    assert parse_max_tokens("1.5k") == 1_500
    assert parse_max_tokens("2w") == 20_000
    assert parse_max_tokens("3m") == 3_000_000


def test_parse_max_tokens_case_insensitive():
    assert parse_max_tokens("10K") == 10_000
    assert parse_max_tokens("1W") == 10_000


def test_parse_max_tokens_zero():
    assert parse_max_tokens("0") == 0


def test_parse_max_tokens_invalid_suffix():
    import click
    with pytest.raises(click.BadParameter):
        parse_max_tokens("10g")


def test_parse_max_tokens_empty():
    import click
    with pytest.raises(click.BadParameter):
        parse_max_tokens("")
