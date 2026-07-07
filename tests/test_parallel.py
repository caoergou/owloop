"""Tests for the file-disjoint parallel worker orchestrator (Phase 4)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from owloop.adapters import AgentResult, MockAdapter
from owloop.parallel import ParallelConfig, ParallelOrchestrator


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _repo_with_specs(tmp_path: Path, specs: dict[str, list[str]]) -> Path:
    """Create a git repo with committed, file-scoped specs (acceptance: `true`)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "T")
    (repo / "README.md").write_text("# t", encoding="utf-8")
    specs_dir = repo / ".owloop" / "specs"
    specs_dir.mkdir(parents=True)
    for name, files in specs.items():
        files_block = "\n".join(f"- {f}" for f in files)
        (specs_dir / name).write_text(
            f"# Spec: {name}\n\n## Priority: 1\n\n## Files\n{files_block}\n\n"
            f"## Acceptance Criteria\n- `true`\n\n## Exclusions\n- Do NOT touch other files\n",
            encoding="utf-8",
        )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init with specs")
    return repo


def _done() -> AgentResult:
    return AgentResult(
        stdout="<promise>DONE</promise>",
        returncode=0,
        success=True,
        has_completion_signal=True,
        done_signal="<promise>DONE</promise>",
    )


def _done_factory():
    return MockAdapter(responses=[_done()])


def _is_complete(repo: Path, spec: str) -> bool:
    from owloop.spec_queue import is_root_spec_complete

    return is_root_spec_complete(repo / ".owloop" / "specs" / spec)


def test_parallel_completes_disjoint_specs(tmp_path: Path) -> None:
    repo = _repo_with_specs(tmp_path, {
        "01-a.md": ["src/a/"],
        "02-b.md": ["src/b/"],
    })
    config = ParallelConfig(project_dir=repo, workers=2)
    events: list[tuple[str, dict]] = []
    orch = ParallelOrchestrator(config, _done_factory, on_event=lambda k, d: events.append((k, d)))

    summary = orch.run()

    assert summary.stopped_reason == "success"
    assert _is_complete(repo, "01-a.md")
    assert _is_complete(repo, "02-b.md")
    # First round scheduled both specs together (disjoint scopes).
    round_starts = [d for k, d in events if k == "round_start"]
    assert round_starts and round_starts[0]["size"] == 2
    assert sum(1 for k, _ in events if k == "worker_merged") == 2


def test_parallel_merges_land_on_base_branch(tmp_path: Path) -> None:
    repo = _repo_with_specs(tmp_path, {"01-a.md": ["src/a/"], "02-b.md": ["src/b/"]})
    orch = ParallelOrchestrator(ParallelConfig(project_dir=repo, workers=2), _done_factory)

    orch.run()

    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=repo, capture_output=True, text=True
    ).stdout
    assert "owloop: complete 01-a.md" in log
    assert "owloop: complete 02-b.md" in log
    # Worktrees are cleaned up.
    assert subprocess.run(
        ["git", "worktree", "list"], cwd=repo, capture_output=True, text=True
    ).stdout.count("owloop-") == 0


def test_parallel_overlapping_specs_run_in_separate_rounds(tmp_path: Path) -> None:
    # Both specs touch src/shared/ → never batched together.
    repo = _repo_with_specs(tmp_path, {
        "01-a.md": ["src/shared/a.py"],
        "02-b.md": ["src/shared/b.py", "src/shared/"],
    })
    # Force conflict: 02 declares the whole dir, 01 a file inside it.
    events: list[tuple[str, dict]] = []
    orch = ParallelOrchestrator(
        ParallelConfig(project_dir=repo, workers=2), _done_factory,
        on_event=lambda k, d: events.append((k, d)),
    )
    summary = orch.run()

    assert summary.stopped_reason == "success"
    sizes = [d["size"] for k, d in events if k == "round_start"]
    assert all(s == 1 for s in sizes)  # never parallelized
    assert len(sizes) == 2  # two sequential rounds


def test_parallel_stalls_when_no_worker_makes_progress(tmp_path: Path) -> None:
    repo = _repo_with_specs(tmp_path, {"01-a.md": ["src/a/"], "02-b.md": ["src/b/"]})

    # Workers never emit DONE → no spec ever completes.
    def _fail_factory():
        return MockAdapter(responses=[AgentResult(
            stdout="nope", returncode=0, success=True, has_completion_signal=False,
        )])

    events: list[tuple[str, dict]] = []
    orch = ParallelOrchestrator(
        ParallelConfig(project_dir=repo, workers=2, max_consecutive_failed_rounds=2),
        _fail_factory, on_event=lambda k, d: events.append((k, d)),
    )
    summary = orch.run()

    assert summary.stopped_reason == "stalled"
    assert summary.state == "stalled"
    assert any(k == "stalled" for k, _ in events)
    assert not _is_complete(repo, "01-a.md")


def test_parallel_preflight_fails_without_specs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "T")
    (repo / ".owloop" / "specs").mkdir(parents=True)
    orch = ParallelOrchestrator(ParallelConfig(project_dir=repo, workers=2), _done_factory)

    summary = orch.run()
    assert summary.stopped_reason == "preflight_failed"
