"""Tests for owloop brand assets and helpers."""

import pytest

from owloop._brand import (
    ASCII_MOON_PHASES,
    MOON_PHASES,
    OWL_BLINK,
    OWL_FACE,
    OWL_MEDIUM,
    OWL_SLEEP,
    OWL_SMALL,
    ascii_moon_for_progress,
    exit_hints,
    moon_for_progress,
    status_message,
)


@pytest.mark.parametrize(
    ("done", "total", "expected"),
    [
        (0, 4, MOON_PHASES[0]),
        (1, 4, MOON_PHASES[1]),
        (2, 4, MOON_PHASES[2]),
        (3, 4, MOON_PHASES[3]),
        (4, 4, MOON_PHASES[4]),
        # boundary checks
        (0, 0, MOON_PHASES[0]),
        (100, 100, MOON_PHASES[4]),
    ],
)
def test_moon_for_progress_phases(done, total, expected):
    assert moon_for_progress(done, total) == expected


@pytest.mark.parametrize(
    ("done", "total", "expected"),
    [
        (0, 4, ASCII_MOON_PHASES[0]),
        (1, 4, ASCII_MOON_PHASES[1]),
        (2, 4, ASCII_MOON_PHASES[2]),
        (3, 4, ASCII_MOON_PHASES[3]),
        (4, 4, ASCII_MOON_PHASES[4]),
        (0, 0, ASCII_MOON_PHASES[0]),
        (100, 100, ASCII_MOON_PHASES[4]),
    ],
)
def test_ascii_moon_for_progress_phases(done, total, expected):
    assert ascii_moon_for_progress(done, total) == expected


@pytest.mark.parametrize(
    ("phase", "iteration", "spec_name", "expected_substring"),
    [
        ("complete", 0, "", "done — time for coffee"),
        ("error", 0, "", "hit a snag"),
        ("stuck", 0, "", "scratching his head"),
        ("done_signal", 3, "", "Iteration 3 closed the loop"),
        ("working", 2, "", "hunting bugs on iteration 2"),
        ("working", 2, "fix-thing.md", "fix-thing.md"),
        ("starting", 0, "", "waking up"),
    ],
)
def test_status_message_phases(phase, iteration, spec_name, expected_substring):
    msg = status_message(phase, iteration=iteration, spec_name=spec_name)
    assert expected_substring in msg


@pytest.mark.parametrize("art", [OWL_SMALL, OWL_MEDIUM, OWL_BLINK, OWL_SLEEP, OWL_FACE])
def test_owl_art_is_rectangular(art):
    assert art
    widths = {len(row) for row in art}
    assert len(widths) == 1, f"inconsistent widths: {widths}"


def test_exit_hints_in_main_repo():
    hints = exit_hints(branch="feat/x", iterations=3, cwd="/repo", main_repo_dir="/repo")
    assert hints == ["Branch: feat/x"]


def test_exit_hints_in_worktree():
    hints = exit_hints(
        branch="feat/x",
        iterations=3,
        cwd="/repo/.worktrees/feat-x",
        main_repo_dir="/repo",
        stopped_reason="max_iterations",
    )
    assert len(hints) == 5
    assert "git log --oneline HEAD~3..HEAD" in hints[0]
    assert "cd /repo && git checkout main && git merge feat/x" in hints[1]
    assert "git push origin main" in hints[2]
    assert "git worktree remove /repo/.worktrees/feat-x && git branch -d feat/x" in hints[3]
    assert "owloop run --resume" in hints[4]


def test_exit_hints_in_worktree_success_omits_resume():
    hints = exit_hints(
        branch="feat/x",
        iterations=3,
        cwd="/repo/.worktrees/feat-x",
        main_repo_dir="/repo",
        stopped_reason="success",
    )
    assert "owloop run --resume" not in hints


def test_exit_hints_with_report_path():
    hints = exit_hints(
        branch="feat/x",
        iterations=3,
        cwd="/repo/.worktrees/feat-x",
        main_repo_dir="/repo",
        report_path="report.md",
    )
    assert hints[0] == "Report:   report.md"


def test_exit_hints_zero_iterations():
    hints = exit_hints(
        branch="feat/x", iterations=0, cwd="/repo/.worktrees/feat-x", main_repo_dir="/repo"
    )
    assert any("git log --oneline -1" in line for line in hints)
