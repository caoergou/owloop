"""Tests for operational learning tracking and fix-loop recovery."""

import subprocess
from pathlib import Path

from owloop.adapters import AgentResult, MockAdapter
from owloop.engine import EngineConfig, OwloopEngine
from owloop.learnings import extract_learnings, load_learnings


def _git_init(repo: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("# test", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)


def test_extract_learnings() -> None:
    stdout = "done\n<learning>tests require a database</learning>\n<promise>DONE</promise>"
    assert extract_learnings(stdout) == ["tests require a database"]


def test_build_prompt_includes_learnings(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    learnings = repo / ".owloop" / "learnings.md"
    learnings.parent.mkdir(parents=True)
    learnings.write_text("## 2024-01-01\nuse poetry not pip\n", encoding="utf-8")

    adapter = MockAdapter()
    config = EngineConfig(project_dir=repo, worktree=False)
    engine = OwloopEngine(config=config, adapter=adapter)

    prompt = engine._build_prompt_with_context("PROMPT")
    assert "use poetry not pip" in prompt
    assert "Operational learnings" in prompt


def test_iteration_records_learning(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / ".owloop" / "specs").mkdir(parents=True)
    (repo / ".owloop" / "specs" / "01-test.md").write_text("# spec", encoding="utf-8")

    adapter = MockAdapter(
        responses=[
            AgentResult(
                stdout="<learning>tests need redis</learning>\n<promise>DONE</promise>",
                returncode=0,
                success=True,
                has_completion_signal=True,
                done_signal="<promise>DONE</promise>",
            )
        ]
    )
    config = EngineConfig(project_dir=repo, worktree=False)
    engine = OwloopEngine(config=config, adapter=adapter)
    engine.log_dir.mkdir(parents=True, exist_ok=True)
    engine.session_log = engine.log_dir / "session.log"
    engine._write_prompt_file()

    engine.run_iteration(1)

    assert "tests need redis" in load_learnings(repo)


class _FileTouchingAdapter(MockAdapter):
    """Agent that rewrites the same file every iteration, then reports DONE.

    The engine commits each verified success itself, so three consecutive
    completed specs that all touch ``file.py`` present as a fix loop across
    real engine commits.
    """

    def __init__(self, repo: Path, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._repo = repo
        self._n = 0

    def run(self, prompt: str, cwd: Path, *, on_line=None) -> AgentResult:
        self._n += 1
        (self._repo / "file.py").write_text(f"v{self._n}", encoding="utf-8")
        return super().run(prompt, cwd, on_line=on_line)


def test_fix_loop_stops_loop(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / "file.py").write_text("a", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "add file"], cwd=repo, check=True, capture_output=True)
    specs_dir = repo / ".owloop" / "specs"
    specs_dir.mkdir(parents=True)
    # Several specs so each success commits (touching file.py) without draining
    # the queue before the fix-loop threshold (3) is reached.
    for i in range(1, 5):
        (specs_dir / f"0{i}-test.md").write_text("# spec", encoding="utf-8")

    adapter = _FileTouchingAdapter(
        repo,
        responses=[
            AgentResult(
                stdout="change\n<promise>DONE</promise>",
                returncode=0,
                success=True,
                has_completion_signal=True,
                done_signal="<promise>DONE</promise>",
            )
            for _ in range(5)
        ],
    )
    config = EngineConfig(project_dir=repo, worktree=False, max_iterations=10)
    engine = OwloopEngine(config=config, adapter=adapter)

    summary = engine.run()

    assert summary.stopped_reason == "fix_loop_blocked"
