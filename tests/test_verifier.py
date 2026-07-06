"""Tests for the independent verifier agent integration."""

import subprocess
from pathlib import Path

from owloop.adapters import AgentResult, MockAdapter
from owloop.engine import EngineConfig, OwloopEngine


def _git_init(repo: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("# test", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)


def _make_engine(repo: Path, adapter: MockAdapter, verifier: MockAdapter | None = None, **kwargs) -> OwloopEngine:
    config = EngineConfig(project_dir=repo, worktree=False, verifier_adapter=verifier, **kwargs)
    return OwloopEngine(config=config, adapter=adapter)


def test_verifier_pass_marks_iteration_success(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / ".owloop" / "specs").mkdir(parents=True)
    (repo / ".owloop" / "specs" / "01-test.md").write_text("# spec", encoding="utf-8")

    executor = MockAdapter(
        responses=[
            AgentResult(
                stdout="done\n<promise>DONE</promise>",
                returncode=0,
                success=True,
                has_completion_signal=True,
                done_signal="<promise>DONE</promise>",
            )
        ]
    )
    verifier = MockAdapter(
        responses=[
            AgentResult(
                stdout="all checks pass\n<promise>PASS</promise>",
                returncode=0,
                success=True,
                has_completion_signal=True,
                done_signal="<promise>PASS</promise>",
                promise_state="PASS",
            )
        ]
    )
    engine = _make_engine(repo, executor, verifier)
    engine.log_dir.mkdir(parents=True, exist_ok=True)
    engine.session_log = engine.log_dir / "session.log"
    engine._write_prompt_file()

    result = engine.run_iteration(1)

    assert result.success
    assert result.promise_state == "DONE"


def test_verifier_fail_marks_iteration_failed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / ".owloop" / "specs").mkdir(parents=True)
    (repo / ".owloop" / "specs" / "01-test.md").write_text("# spec", encoding="utf-8")

    executor = MockAdapter(
        responses=[
            AgentResult(
                stdout="done\n<promise>DONE</promise>",
                returncode=0,
                success=True,
                has_completion_signal=True,
                done_signal="<promise>DONE</promise>",
            )
        ]
    )
    verifier = MockAdapter(
        responses=[
            AgentResult(
                stdout="test missing\n<promise>FAIL:test not found</promise>",
                returncode=0,
                success=True,
                has_completion_signal=True,
                done_signal="<promise>FAIL:test not found</promise>",
                promise_state="FAIL",
                promise_payload="test not found",
            )
        ]
    )
    engine = _make_engine(repo, executor, verifier)
    engine.log_dir.mkdir(parents=True, exist_ok=True)
    engine.session_log = engine.log_dir / "session.log"
    engine._write_prompt_file()

    result = engine.run_iteration(1)

    assert not result.success
    assert result.promise_state == "VERIFY_FAIL"
    assert "test not found" in result.promise_payload


def test_no_verifier_keeps_existing_behavior(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / ".owloop" / "specs").mkdir(parents=True)
    (repo / ".owloop" / "specs" / "01-test.md").write_text("# spec", encoding="utf-8")

    executor = MockAdapter(
        responses=[
            AgentResult(
                stdout="done\n<promise>DONE</promise>",
                returncode=0,
                success=True,
                has_completion_signal=True,
                done_signal="<promise>DONE</promise>",
            )
        ]
    )
    engine = _make_engine(repo, executor)
    engine.log_dir.mkdir(parents=True, exist_ok=True)
    engine.session_log = engine.log_dir / "session.log"
    engine._write_prompt_file()

    result = engine.run_iteration(1)

    assert result.success
    assert result.promise_state == "DONE"
