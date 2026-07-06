"""Tests for the owloop CLI entry points."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version

import pytest
from click.testing import CliRunner, _NamedTextIOWrapper

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
    assert "owloop go" in result.output
    assert "owloop run" in result.output


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


def test_go_help_exposes_run_options():
    runner = CliRunner()
    result = runner.invoke(main, ["go", "--help"])
    assert result.exit_code == 0
    for option in (
        "--agent",
        "--model",
        "--verifier-model",
        "--subagents",
        "--idle-timeout",
        "--max-duration",
        "--max-tokens",
        "--worktree",
        "--no-worktree",
    ):
        assert option in result.output, f"{option} should appear in owloop go --help"


def test_go_forwards_options_to_engine_runner():
    from unittest.mock import MagicMock, patch

    runner = CliRunner()
    with runner.isolated_filesystem():
        import subprocess
        subprocess.run(["git", "init"], check=True, capture_output=True)

        with (
            patch.object(_NamedTextIOWrapper, "isatty", return_value=True),
            patch("owloop.cli._run_engine") as mock_engine,
            patch("owloop.cli.Confirm.ask", return_value=True),
            patch("owloop.cli.SpecGenerator") as mock_gen,
            patch("owloop.cli.get_adapter") as mock_adapter,
        ):
            mock_gen.return_value.generate.return_value = []
            mock_adapter.return_value = MagicMock()
            result = runner.invoke(main, [
                "go", "test goal",
                "--agent=kimi",
                "--model=test-model",
                "--verifier-model=v-model",
                "--subagents",
                "--idle-timeout=120",
                "--max-duration=30",
                "--max-tokens=10k",
                "--no-worktree",
            ])
            assert result.exit_code == 0, result.output
            mock_engine.assert_called_once()
            args, kwargs = mock_engine.call_args
            assert args[0] == 0
            assert args[1] is False
            assert args[2] == "test-model"
            assert args[3] == "kimi"
            assert args[4] == 120.0
            assert args[5] == 30
            assert args[6] == 10000
            assert kwargs.get("verifier_model") == "v-model"
            assert kwargs.get("subagents") is True
            assert kwargs.get("ascii") is False
            assert kwargs.get("no_color") is False
            assert kwargs.get("compact") is False
