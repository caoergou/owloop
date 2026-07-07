"""Tests for Phase 1 of the loop-engineering roadmap (issues #32/#33/#34/#35).

Covers the deterministic verification gate, named terminal states + stall
detection, failed-iteration rollback, and native per-iteration limit handling.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from owloop.adapters import AgentResult, MockAdapter
from owloop.engine import (
    EngineConfig,
    OwloopEngine,
    TerminalState,
    classify_terminal_state,
)


def _git_init(repo: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("# test", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)


def _spec(specs_dir: Path, name: str, criterion: str) -> None:
    specs_dir.mkdir(parents=True, exist_ok=True)
    (specs_dir / name).write_text(
        f"# Spec: {name}\n\n## Acceptance Criteria\n- check: `{criterion}`\n",
        encoding="utf-8",
    )


def _done(**kw) -> AgentResult:
    return AgentResult(
        stdout="work done\n<promise>DONE</promise>",
        returncode=0,
        success=True,
        has_completion_signal=True,
        done_signal="<promise>DONE</promise>",
        **kw,
    )


def _adapter_with_file(path: Path | str = "src/change.py", **kw) -> MockAdapter:
    """Return a MockAdapter that creates a source file before returning DONE."""
    adapter = MockAdapter(responses=[_done(**kw)])
    original_run = adapter.run

    def _run(prompt: str, cwd: Path, *, on_line=None):
        target = cwd / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# changed\n", encoding="utf-8")
        return original_run(prompt, cwd, on_line=on_line)

    adapter.run = _run  # type: ignore[method-assign]
    return adapter


def _make(repo: Path, adapter: MockAdapter, **kwargs) -> OwloopEngine:
    return OwloopEngine(EngineConfig(project_dir=repo, worktree=False, **kwargs), adapter)


# ── Terminal-state taxonomy (#33) ──


def test_classify_terminal_state_maps_reasons() -> None:
    assert classify_terminal_state("success") == TerminalState.SUCCESS
    assert classify_terminal_state("all_specs_complete") == TerminalState.SUCCESS
    assert classify_terminal_state("max_tokens") == TerminalState.EXHAUSTED
    assert classify_terminal_state("max_iterations") == TerminalState.EXHAUSTED
    assert classify_terminal_state("stalled") == TerminalState.STALLED
    assert classify_terminal_state("tampered") == TerminalState.TAMPERED
    assert classify_terminal_state("unknown-reason") == TerminalState.FAILED


def test_exhausted_is_never_success() -> None:
    for reason in ("max_iterations", "max_duration", "max_tokens"):
        state = classify_terminal_state(reason)
        assert state == TerminalState.EXHAUSTED
        assert state != TerminalState.SUCCESS


# ── Deterministic verification gate (#32) ──


def test_gate_pass_commits_and_marks_complete(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _spec(repo / ".owloop" / "specs", "01-t.md", "true")  # criterion passes
    monkeypatch.setattr("owloop.engine.time.sleep", lambda _: None)

    engine = _make(repo, _adapter_with_file(), max_iterations=1)
    pushes: list[str] = []
    monkeypatch.setattr(engine, "_push", lambda b: pushes.append(b))

    summary = engine.run()

    assert summary.stopped_reason == "success"
    assert summary.state == TerminalState.SUCCESS
    # Engine — not the agent — flipped the status and committed.
    assert "**Status**: COMPLETE" in (repo / ".owloop" / "specs" / "01-t.md").read_text()
    assert pushes == [summary.branch]  # pushed exactly once, on success
    last = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    # Commit messages use the spec title from ``# Spec: <title>``.
    assert last == "01-t.md"


def test_gate_fail_no_commit_no_push(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _spec(repo / ".owloop" / "specs", "01-t.md", "false")  # criterion fails
    monkeypatch.setattr("owloop.engine.time.sleep", lambda _: None)

    head_before = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()

    engine = _make(repo, MockAdapter(responses=[_done()]), max_iterations=1)
    pushes: list[str] = []
    monkeypatch.setattr(engine, "_push", lambda b: pushes.append(b))
    events: list[str] = []
    engine.on_event = lambda k, d: events.append(k)

    summary = engine.run()

    assert "verification_gate_failed" in events
    assert pushes == []  # a failed gate never pushes
    head_after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    assert head_after == head_before  # and never commits
    assert "**Status**: COMPLETE" not in (repo / ".owloop" / "specs" / "01-t.md").read_text()
    assert summary.stopped_reason == "max_iterations"


class _TamperAdapter(MockAdapter):
    """Agent that rewrites its own acceptance criteria mid-iteration."""

    def __init__(self, spec_file: Path, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._spec_file = spec_file

    def run(self, prompt: str, cwd: Path, *, on_line=None) -> AgentResult:
        self._spec_file.write_text(
            "# Spec\n\n## Acceptance Criteria\n- check: `true`\n", encoding="utf-8"
        )
        return super().run(prompt, cwd, on_line=on_line)


def test_gate_detects_tampering(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    specs = repo / ".owloop" / "specs"
    _spec(specs, "01-t.md", "false")  # originally fails; agent will rewrite to `true`
    monkeypatch.setattr("owloop.engine.time.sleep", lambda _: None)

    adapter = _TamperAdapter(specs / "01-t.md", responses=[_done()])
    engine = _make(repo, adapter, max_iterations=1)
    events: list[str] = []
    engine.on_event = lambda k, d: events.append(k)

    engine.run()

    assert "spec_tampered" in events
    # Rewriting acceptance criteria fails the iteration even though `true` passes.
    assert "verification_gate_passed" not in events


# ── Hard stop on stall (#33) ──


def _fail() -> AgentResult:
    return AgentResult(stdout="boom", returncode=1, success=False, has_completion_signal=False)


def test_consecutive_failures_stall(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _spec(repo / ".owloop" / "specs", "01-t.md", "true")
    monkeypatch.setattr("owloop.engine.time.sleep", lambda _: None)

    engine = _make(
        repo,
        MockAdapter(responses=[_fail() for _ in range(10)]),
        max_iterations=0,  # unlimited — only the stall stops it
        max_consecutive_failures=3,
    )
    events: list[str] = []
    engine.on_event = lambda k, d: events.append(k)

    summary = engine.run()

    assert summary.stopped_reason == "stalled"
    assert summary.state == TerminalState.STALLED
    assert summary.iterations == 3
    assert "stalled" in events


def test_keep_retrying_disables_stall(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _spec(repo / ".owloop" / "specs", "01-t.md", "true")
    monkeypatch.setattr("owloop.engine.time.sleep", lambda _: None)

    engine = _make(
        repo,
        MockAdapter(responses=[_fail() for _ in range(5)]),
        max_iterations=5,
        max_consecutive_failures=3,
        keep_retrying=True,
    )
    summary = engine.run()

    # Never stalls; runs to the iteration cap instead.
    assert summary.iterations == 5
    assert summary.stopped_reason == "max_iterations"


def test_same_error_stall(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _spec(repo / ".owloop" / "specs", "01-t.md", "true")
    monkeypatch.setattr("owloop.engine.time.sleep", lambda _: None)

    # No-signal successes (not consecutive *crashes*) with an identical tail:
    # consecutive-failure limit and same-error limit both apply; set the
    # consecutive limit high so the same-error counter is what trips.
    no_signal = AgentResult(stdout="same tail 12", returncode=0, success=True, has_completion_signal=False)
    engine = _make(
        repo,
        MockAdapter(responses=[no_signal for _ in range(10)]),
        max_iterations=0,
        max_consecutive_failures=99,
        max_same_error_count=4,
    )
    events: list[tuple[str, dict]] = []
    engine.on_event = lambda k, d: events.append((k, d))

    summary = engine.run()

    assert summary.stopped_reason == "stalled"
    assert summary.iterations == 4
    assert any(k == "stalled" and d.get("reason") == "same_error" for k, d in events)


# ── Rollback of failed iterations (#34) ──


class _MessyAdapter(MockAdapter):
    """Agent that leaves junk files and edits before failing (no DONE)."""

    def __init__(self, repo: Path, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._repo = repo

    def run(self, prompt: str, cwd: Path, *, on_line=None) -> AgentResult:
        (self._repo / "half_done.py").write_text("garbage", encoding="utf-8")
        (self._repo / "README.md").write_text("corrupted", encoding="utf-8")
        return super().run(prompt, cwd, on_line=on_line)


def test_rollback_cleans_workspace_and_saves_patch(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _spec(repo / ".owloop" / "specs", "01-t.md", "true")
    monkeypatch.setattr("owloop.engine.time.sleep", lambda _: None)

    adapter = _MessyAdapter(repo, responses=[_fail()])
    engine = _make(repo, adapter, max_iterations=1)
    engine.run()

    # Working tree restored to the last good commit.
    assert not (repo / "half_done.py").exists()
    assert (repo / "README.md").read_text() == "# test"
    # Discarded work preserved as a patch.
    patch = engine.log_dir / "iter_1_discarded.patch"
    assert patch.is_file()
    assert "half_done.py" in patch.read_text()


def test_no_rollback_preserves_workspace(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _spec(repo / ".owloop" / "specs", "01-t.md", "true")
    monkeypatch.setattr("owloop.engine.time.sleep", lambda _: None)

    adapter = _MessyAdapter(repo, responses=[_fail()])
    engine = _make(repo, adapter, max_iterations=1, rollback=False)
    events: list[str] = []
    engine.on_event = lambda k, d: events.append(k)
    engine.run()

    assert (repo / "half_done.py").exists()  # opt-out keeps partial work
    assert "rollback_skipped" in events


def test_run_notes_relocated_under_owloop(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _spec(repo / ".owloop" / "specs", "01-t.md", "true")
    monkeypatch.setattr("owloop.engine.time.sleep", lambda _: None)

    engine = _make(repo, MockAdapter(responses=[_done()]), max_iterations=1)
    monkeypatch.setattr(engine, "_push", lambda b: None)
    engine.run()

    assert (repo / ".owloop" / "run-notes.md").is_file()
    assert not (repo / "run-notes.md").exists()
    # Loop metadata never enters the engine's commit.
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=repo, capture_output=True, text=True
    ).stdout
    assert "run-notes.md" not in tracked
