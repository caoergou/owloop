"""Tests for the owloop CLI entry points."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version

from click.testing import CliRunner

from owloop.cli import main


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
    assert "owloop plan" in result.output
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
        assert "No specs/" in result.output


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
