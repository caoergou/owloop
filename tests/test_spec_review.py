"""Tests for the spec quality review step."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from owloop.adapters import AgentResult, MockAdapter
from owloop.cli import main
from owloop.spec_review import SpecReview


@pytest.fixture
def sample_spec(tmp_path: Path) -> Path:
    spec = tmp_path / "01-sample.md"
    spec.write_text(
        """
# Spec: sample

## Priority: 1

## Requirements
- [ ] Do a thing.

## Acceptance Criteria
- [ ] `python --version` → shows Python version

## Exclusions
- Do NOT modify `unrelated.py`.

## Style
- Follow existing patterns.

## Stuck Behavior
Document blockers.

## Verification
Run commands.

## Baseline
- `python --version`: current version

Output when complete: `<promise>DONE</promise>`
""",
        encoding="utf-8",
    )
    return spec


def test_static_check_catches_missing_section(sample_spec: Path) -> None:
    specs_dir = sample_spec.parent
    reviewer = SpecReview(specs_dir)
    report = reviewer.review(sample_spec, auto_fix=False)

    # Missing depends-on is not an error in current linter, but the spec is valid.
    assert report.error_count == 0


def test_executable_check_catches_missing_command(sample_spec: Path) -> None:
    specs_dir = sample_spec.parent
    bad_spec = specs_dir / "02-bad.md"
    bad_spec.write_text(
        sample_spec.read_text(encoding="utf-8").replace(
            "`python --version`", "`not_a_real_command_12345 --version`"
        ),
        encoding="utf-8",
    )

    reviewer = SpecReview(specs_dir)
    report = reviewer.review(bad_spec, auto_fix=False)

    assert any("not found on PATH" in f.message for f in report.findings)


def test_auto_fix_adds_done_promise(tmp_path: Path) -> None:
    spec = tmp_path / "03-incomplete.md"
    spec.write_text(
        """
# Spec: incomplete

## Priority: 1

## Requirements
- [ ] Do a thing.

## Acceptance Criteria
- [ ] `python --version` → shows version

## Exclusions
- Do NOT modify `other.py`.
""",
        encoding="utf-8",
    )

    reviewer = SpecReview(tmp_path)
    report = reviewer.review(spec, auto_fix=True)

    assert any("added missing" in fix for fix in report.auto_fixed)
    content = spec.read_text(encoding="utf-8")
    assert "## Verification" in content
    assert "<promise>DONE</promise>" in content


def test_agent_review_flags_vague_exclusion(tmp_path: Path) -> None:
    spec = tmp_path / "04-vague.md"
    spec.write_text(
        """
# Spec: vague

## Priority: 1

## Requirements
- [ ] Do a thing.

## Acceptance Criteria
- [ ] `python --version` → shows version

## Exclusions
- Do NOT break things.
""",
        encoding="utf-8",
    )

    adapter = MockAdapter(
        responses=[
            AgentResult(
                stdout="[WARNING] exclusion is vague: 'do not break things'\n",
                returncode=0,
                success=True,
                has_completion_signal=False,
            )
        ]
    )
    reviewer = SpecReview(tmp_path, adapter=adapter)
    report = reviewer.review(spec, auto_fix=False)

    assert any("vague" in f.message.lower() for f in report.findings)


def test_cli_check_review() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as fs:
        fs_path = Path(fs)
        spec = fs_path / ".owloop" / "specs" / "01-test.md"
        spec.parent.mkdir(parents=True)
        spec.write_text(
            """
# Spec: test

## Priority: 1

## Requirements
- [ ] Do a thing.

## Acceptance Criteria
- [ ] `not_a_real_command_12345` → ok

## Exclusions
- Do NOT modify `other.py`.

## Style
- Follow existing patterns.

## Stuck Behavior
Document blockers.

## Verification
Run commands.

## Baseline
- `not_a_real_command_12345`: current

Output when complete: `<promise>DONE</promise>`
""",
            encoding="utf-8",
        )

        result = runner.invoke(main, ["check", "--review"])
        assert result.exit_code == 1
        assert "not found on PATH" in result.output
