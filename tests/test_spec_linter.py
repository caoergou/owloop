"""Tests for the owloop spec linter and `owloop check` CLI."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from owloop.cli import main
from owloop.spec_linter import SpecLinter


def _write_spec(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


VALID_SPEC = """\
# Spec: valid-task

## Priority: 1

## Requirements
Add a helper function.

## Acceptance Criteria
- [ ] `echo ok` → prints ok

## Exclusions
- Do NOT modify unrelated files

## Verification
Run the test suite.

## Baseline
- [echo ok]: 0 → target 0

<promise>DONE</promise>
"""


def test_valid_spec_passes(tmp_path: Path) -> None:
    specs_dir = tmp_path / "specs"
    _write_spec(specs_dir / "001-valid.md", VALID_SPEC)

    linter = SpecLinter(specs_dir)
    report = linter.lint_all()

    assert report.error_count == 0
    assert report.results["001-valid.md"] == []


def test_missing_exclusions_fails(tmp_path: Path) -> None:
    specs_dir = tmp_path / "specs"
    content = VALID_SPEC.replace("## Exclusions\n- Do NOT modify unrelated files\n", "")
    _write_spec(specs_dir / "001-missing-exclusions.md", content)

    linter = SpecLinter(specs_dir)
    report = linter.lint_all()

    assert report.error_count == 1
    assert any("Exclusions section is empty" in f.message for f in report.results["001-missing-exclusions.md"])


def test_vague_acceptance_criterion_fails(tmp_path: Path) -> None:
    specs_dir = tmp_path / "specs"
    content = VALID_SPEC.replace(
        "- [ ] `echo ok` → prints ok",
        '- [ ] Error handling is properly unified',
    )
    _write_spec(specs_dir / "001-vague.md", content)

    linter = SpecLinter(specs_dir)
    report = linter.lint_all()

    assert any("vague" in f.message for f in report.results["001-vague.md"])


def test_missing_backtick_command_fails(tmp_path: Path) -> None:
    specs_dir = tmp_path / "specs"
    content = VALID_SPEC.replace(
        "- [ ] `echo ok` → prints ok",
        "- [ ] grep something without backticks",
    )
    _write_spec(specs_dir / "001-no-backtick.md", content)

    linter = SpecLinter(specs_dir)
    report = linter.lint_all()

    assert any("no shell command in criterion" in f.message for f in report.results["001-no-backtick.md"])


def test_contradiction_between_exclusions_and_requirements(tmp_path: Path) -> None:
    specs_dir = tmp_path / "specs"
    content = VALID_SPEC.replace(
        "## Requirements\nAdd a helper function.",
        "## Requirements\nRefactor backend/app/api.py.",
    ).replace(
        "## Exclusions\n- Do NOT modify unrelated files",
        "## Exclusions\n- Do NOT modify backend/app/api.py",
    )
    _write_spec(specs_dir / "001-contradiction.md", content)

    linter = SpecLinter(specs_dir)
    report = linter.lint_all()

    assert any("contradiction" in f.message for f in report.results["001-contradiction.md"])


def test_strict_turns_warnings_into_errors(tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as fs:
        specs_dir = Path(fs) / "specs"
        # Valid structure but missing optional warning sections.
        minimal = """\
# Spec: minimal

## Priority: 2

## Requirements
Do a thing.

## Acceptance Criteria
- [ ] `true` → ok

## Exclusions
- Do NOT touch unrelated files
"""
        _write_spec(specs_dir / "001-minimal.md", minimal)

        result = runner.invoke(main, ["check"])
        assert result.exit_code == 0
        assert "warning" in result.output.lower()

        result_strict = runner.invoke(main, ["check", "--strict"])
        assert result_strict.exit_code == 1


def test_run_baseline_executes_baseline_commands(tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as fs:
        specs_dir = Path(fs) / "specs"
        marker = Path(fs) / "baseline-ran"
        spec = f"""\
# Spec: baseline-test

## Priority: 1

## Requirements
Do a thing.

## Acceptance Criteria
- [ ] `true` → ok

## Exclusions
- Do NOT touch unrelated files

## Baseline
- [touch {marker}]: marker missing → target marker present

<promise>DONE</promise>
"""
        _write_spec(specs_dir / "001-baseline.md", spec)

        result = runner.invoke(main, ["check", "--run-baseline"])
        assert result.exit_code == 0, result.output
        assert marker.exists()


def test_circular_spec_dependency_fails(tmp_path: Path) -> None:
    specs_dir = tmp_path / "specs"
    spec_a = VALID_SPEC.replace(
        "## Priority: 1\n",
        "## Priority: 1\n\n## Depends On\n- 002-b\n",
    )
    spec_b = VALID_SPEC.replace(
        "## Priority: 1\n",
        "## Priority: 2\n\n## Depends On\n- 001-a\n",
    )
    _write_spec(specs_dir / "001-a.md", spec_a)
    _write_spec(specs_dir / "002-b.md", spec_b)

    linter = SpecLinter(specs_dir)
    report = linter.lint_all()

    assert report.error_count > 0
    all_messages = [f.message for findings in report.results.values() for f in findings]
    assert any("circular" in message.lower() for message in all_messages)
    assert any("001-a.md" in message for message in all_messages)
    assert any("002-b.md" in message for message in all_messages)


def test_run_baseline_reports_failed_commands(tmp_path: Path) -> None:
    specs_dir = tmp_path / "specs"
    content = VALID_SPEC.replace(
        "## Baseline\n- [echo ok]: 0 → target 0",
        "## Baseline\n- [false]: 0 → target 0",
    )
    _write_spec(specs_dir / "001-baseline-fail.md", content)

    linter = SpecLinter(specs_dir)
    report = linter.lint_all(run_baseline=True)

    assert any("baseline command failed" in f.message for f in report.results["001-baseline-fail.md"])
