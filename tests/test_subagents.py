"""Tests for subagent orchestration in build iterations."""

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


def test_subagent_mode_runs_orient_implement_verify(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / ".owloop" / "specs").mkdir(parents=True)
    (repo / ".owloop" / "specs" / "01-test.md").write_text("# spec", encoding="utf-8")

    adapter = MockAdapter(
        responses=[
            AgentResult(
                stdout="plan: modify src/a.py\n<promise>DONE</promise>",
                returncode=0,
                success=True,
                has_completion_signal=True,
                done_signal="<promise>DONE</promise>",
            ),
            AgentResult(
                stdout="implemented\n<promise>DONE</promise>",
                returncode=0,
                success=True,
                has_completion_signal=True,
                done_signal="<promise>DONE</promise>",
            ),
        ]
    )
    verifier = MockAdapter(
        responses=[
            AgentResult(
                stdout="pass\n<promise>PASS</promise>",
                returncode=0,
                success=True,
                has_completion_signal=True,
                done_signal="<promise>PASS</promise>",
                promise_state="PASS",
            )
        ]
    )

    config = EngineConfig(
        project_dir=repo,
        worktree=False,
        use_subagents=True,
        verifier_adapter=verifier,
    )
    engine = OwloopEngine(config=config, adapter=adapter)
    engine.log_dir.mkdir(parents=True, exist_ok=True)
    engine.session_log = engine.log_dir / "session.log"
    engine._write_prompt_file()

    result = engine.run_iteration(1)

    assert result.success
    assert "## Orient" in result.stdout
    assert "## Implement" in result.stdout
    assert "## Verify" in result.stdout
    assert len(adapter.calls) == 2


def test_subagent_mode_skipped_when_disabled(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / ".owloop" / "specs").mkdir(parents=True)
    (repo / ".owloop" / "specs" / "01-test.md").write_text("# spec", encoding="utf-8")

    adapter = MockAdapter(
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

    config = EngineConfig(project_dir=repo, worktree=False, use_subagents=False)
    engine = OwloopEngine(config=config, adapter=adapter)
    engine.log_dir.mkdir(parents=True, exist_ok=True)
    engine.session_log = engine.log_dir / "session.log"
    engine._write_prompt_file()

    result = engine.run_iteration(1)

    assert result.success
    assert "## Orient" not in result.stdout
    assert len(adapter.calls) == 1
