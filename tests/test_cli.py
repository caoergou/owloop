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


def test_run_help_exposes_dry_run_flag():
    runner = CliRunner()
    result = runner.invoke(main, ["run", "--help"])
    assert result.exit_code == 0
    assert "--dry-run" in result.output
    assert "--one-shot" in result.output


def test_run_help_exposes_no_tui_and_plain_flags():
    runner = CliRunner()
    result = runner.invoke(main, ["run", "--help"])
    assert result.exit_code == 0
    assert "--no-tui" in result.output
    assert "--plain" in result.output


def _init_repo_with_spec():
    import subprocess
    from pathlib import Path
    subprocess.run(["git", "init"], check=True, capture_output=True)
    Path(".owloop/specs").mkdir(parents=True)
    Path(".owloop/specs/01-test.md").write_text("# spec\n", encoding="utf-8")


def test_run_dry_run_flag_forwards_to_engine_runner():
    from unittest.mock import patch

    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_repo_with_spec()
        with patch("owloop.cli._run_engine") as mock_engine:
            result = runner.invoke(main, ["run", "--dry-run"])
            assert result.exit_code == 0, result.output
            mock_engine.assert_called_once()
            _args, kwargs = mock_engine.call_args
            assert kwargs.get("dry_run") is True


def test_run_one_shot_alias_forwards_dry_run():
    from unittest.mock import patch

    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_repo_with_spec()
        with patch("owloop.cli._run_engine") as mock_engine:
            result = runner.invoke(main, ["run", "--one-shot"])
            assert result.exit_code == 0, result.output
            _args, kwargs = mock_engine.call_args
            assert kwargs.get("dry_run") is True


def test_run_without_dry_run_flag_defaults_false():
    from unittest.mock import patch

    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_repo_with_spec()
        with patch("owloop.cli._run_engine") as mock_engine:
            result = runner.invoke(main, ["run"])
            assert result.exit_code == 0, result.output
            _args, kwargs = mock_engine.call_args
            assert kwargs.get("dry_run") is False


def test_run_no_tui_flag_forwards_to_engine_runner():
    from unittest.mock import patch

    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_repo_with_spec()
        with patch("owloop.cli._run_engine") as mock_engine:
            result = runner.invoke(main, ["run", "--no-tui"])
            assert result.exit_code == 0, result.output
            _args, kwargs = mock_engine.call_args
            assert kwargs.get("no_tui") is True


def test_run_plain_alias_forwards_no_tui():
    from unittest.mock import patch

    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_repo_with_spec()
        with patch("owloop.cli._run_engine") as mock_engine:
            result = runner.invoke(main, ["run", "--plain"])
            assert result.exit_code == 0, result.output
            _args, kwargs = mock_engine.call_args
            assert kwargs.get("no_tui") is True


def test_run_without_no_tui_flag_defaults_false():
    from unittest.mock import patch

    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_repo_with_spec()
        with patch("owloop.cli._run_engine") as mock_engine:
            result = runner.invoke(main, ["run"])
            assert result.exit_code == 0, result.output
            _args, kwargs = mock_engine.call_args
            assert kwargs.get("no_tui") is False


def test_run_engine_no_tui_bypasses_tui_and_uses_console_reporter():
    from pathlib import Path
    from unittest.mock import MagicMock, patch

    from owloop.cli import _run_engine
    from owloop.engine import RunSummary

    summary = RunSummary(
        iterations=0,
        branch="main",
        cwd=Path("."),
        main_repo_dir=Path("."),
        stopped_reason="max_iterations_reached",
    )
    fake_engine = MagicMock()
    fake_engine.run.return_value = summary

    with (
        patch("owloop.cli.get_adapter"),
        patch("owloop.cli.OwloopEngine", return_value=fake_engine) as mock_engine_cls,
        patch("owloop.cli.OwloopTUI") as mock_tui_cls,
        patch("owloop.cli.ConsoleReporter") as mock_reporter_cls,
        patch("sys.stdout.isatty", return_value=True),
    ):
        _run_engine(0, True, "claude-model", "claude", no_tui=True)

    mock_tui_cls.assert_not_called()
    mock_reporter_cls.assert_called_once()
    mock_engine_cls.assert_called_once()


def test_run_engine_no_tui_preserves_confirm_prompts():
    from pathlib import Path
    from unittest.mock import MagicMock, patch

    from owloop.cli import _run_engine
    from owloop.engine import RunSummary

    captured_config = {}

    def _fake_engine_ctor(config, adapter, on_event=None):
        captured_config["config"] = config
        engine = MagicMock()
        engine.run.return_value = RunSummary(
            iterations=0, branch="main", cwd=Path("."), main_repo_dir=Path("."),
            stopped_reason="max_iterations_reached",
        )
        return engine

    with (
        patch("owloop.cli.get_adapter"),
        patch("owloop.cli.OwloopEngine", side_effect=_fake_engine_ctor),
        patch("owloop.cli.ConsoleReporter"),
        patch("sys.stdout.isatty", return_value=True),
        patch("owloop.cli.Confirm.ask", return_value=True) as mock_confirm,
    ):
        _run_engine(0, True, "claude-model", "claude", no_tui=True)

        config = captured_config["config"]
        assert config.confirm_dirty is not None
        assert config.confirm_worktree is not None
        assert config.confirm_dirty() is True
        assert config.confirm_worktree() is True
        assert mock_confirm.call_count == 2


def test_print_dry_run_report_shows_pass_fail_counts():
    import io
    from pathlib import Path

    from rich.console import Console

    from owloop.cli import _print_dry_run_report
    from owloop.engine import DryRunReport, RunSummary

    buffer = io.StringIO()
    console = Console(no_color=True, file=buffer, width=100)
    summary = RunSummary(
        iterations=1,
        branch="main",
        cwd=Path("."),
        main_repo_dir=Path("."),
        stopped_reason="dry_run_complete",
        tokens_used=42,
        dry_run_report=DryRunReport(
            promise_done=True,
            acceptance_passed=2,
            acceptance_failed=1,
            tokens_used=42,
            spec_name="01-test.md",
        ),
    )

    _print_dry_run_report(console, summary)

    output = buffer.getvalue()
    assert "Dry-run report" in output
    assert "2 passed" in output
    assert "1 failed" in output
    assert "01-test.md" in output


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
