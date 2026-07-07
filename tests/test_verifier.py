"""Tests for the independent verifier agent integration.

The LLM verifier runs *after* the deterministic verification gate
(shell-first ordering): mechanically-broken work never pays for the extra
model roundtrip, and only gate-surviving work gets the second opinion.
"""

import subprocess
from pathlib import Path

from owloop import verification
from owloop.adapters import AgentResult, MockAdapter
from owloop.engine import EngineConfig, OwloopEngine


def _git_init(repo: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("# test", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)


def _spec(repo: Path, criterion: str = "true") -> None:
    specs = repo / ".owloop" / "specs"
    specs.mkdir(parents=True)
    (specs / "01-test.md").write_text(
        f"# Spec\n\n## Acceptance Criteria\n- check: `{criterion}`\n",
        encoding="utf-8",
    )


def _done() -> AgentResult:
    return AgentResult(
        stdout="done\n<promise>DONE</promise>",
        returncode=0,
        success=True,
        has_completion_signal=True,
        done_signal="<promise>DONE</promise>",
    )


def _verifier(state: str, payload: str = "") -> MockAdapter:
    signal = f"<promise>{state}{':' + payload if payload else ''}</promise>"
    return MockAdapter(
        responses=[
            AgentResult(
                stdout=f"checked\n{signal}",
                returncode=0,
                success=True,
                has_completion_signal=True,
                done_signal=signal,
                promise_state=state,
                promise_payload=payload,
            )
        ]
    )


def _make_engine(repo: Path, adapter: MockAdapter, verifier: MockAdapter | None = None, **kwargs) -> OwloopEngine:
    config = EngineConfig(
        project_dir=repo, worktree=False, verifier_adapter=verifier, max_iterations=1, **kwargs
    )
    return OwloopEngine(config=config, adapter=adapter)


def test_verifier_pass_keeps_verified_success(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _spec(repo)
    monkeypatch.setattr("owloop.engine.time.sleep", lambda _: None)

    verifier = _verifier("PASS")
    engine = _make_engine(repo, MockAdapter(responses=[_done()]), verifier)
    monkeypatch.setattr(engine, "_push", lambda b: None)

    summary = engine.run()

    assert summary.stopped_reason == "success"
    assert len(verifier.calls) == 1  # consulted exactly once, after the gate
    assert "**Status**: COMPLETE" in (repo / ".owloop" / "specs" / "01-test.md").read_text()


def test_verifier_fail_marks_iteration_failed(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _spec(repo)
    monkeypatch.setattr("owloop.engine.time.sleep", lambda _: None)

    verifier = _verifier("FAIL", "test not found")
    engine = _make_engine(repo, MockAdapter(responses=[_done()]), verifier)
    pushes: list[str] = []
    monkeypatch.setattr(engine, "_push", lambda b: pushes.append(b))
    events: list[str] = []
    engine.on_event = lambda k, d: events.append(k)

    summary = engine.run()

    assert "verification_failed" in events
    assert pushes == []  # verifier FAIL means no commit, no push
    assert "**Status**: COMPLETE" not in (repo / ".owloop" / "specs" / "01-test.md").read_text()
    assert summary.stopped_reason == "max_iterations"
    # The verifier's verdict feeds the next iteration's failure feedback.
    assert "test not found" in (repo / ".owloop" / "last-failure.md").read_text()


def test_verifier_skipped_when_gate_fails(tmp_path: Path, monkeypatch) -> None:
    """Shell-first ordering: a failing mechanical gate never spawns the verifier."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _spec(repo, criterion="false")  # gate fails deterministically
    monkeypatch.setattr("owloop.engine.time.sleep", lambda _: None)

    verifier = _verifier("PASS")
    engine = _make_engine(repo, MockAdapter(responses=[_done()]), verifier)
    events: list[str] = []
    engine.on_event = lambda k, d: events.append(k)

    engine.run()

    assert "verification_gate_failed" in events
    assert verifier.calls == []  # the expensive model roundtrip was never paid


def test_no_verifier_keeps_existing_behavior(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _spec(repo)
    monkeypatch.setattr("owloop.engine.time.sleep", lambda _: None)

    engine = _make_engine(repo, MockAdapter(responses=[_done()]))
    monkeypatch.setattr(engine, "_push", lambda b: None)

    summary = engine.run()

    assert summary.stopped_reason == "success"


# ── deterministic gate: no-output expectations ──


def test_run_acceptance_criteria_treats_grep_no_match_as_pass(tmp_path: Path) -> None:
    """A `→ no output` criterion must pass when grep finds nothing (exit 1)."""
    specs = tmp_path / ".owloop" / "specs"
    specs.mkdir(parents=True)
    spec = specs / "01-test.md"
    target = tmp_path / "api.py"
    target.write_text("def keep(): pass\n", encoding="utf-8")
    spec.write_text(
        "# Spec\n\n## Acceptance Criteria\n"
        f"- `grep removed {target.name}` → no output\n",
        encoding="utf-8",
    )

    passed, failed, failures = verification.run_acceptance_criteria(
        tmp_path, specs, "01-test.md"
    )

    assert passed == 1
    assert failed == 0
    assert failures == []


def test_run_acceptance_criteria_no_output_fails_on_nonempty_stdout(tmp_path: Path) -> None:
    specs = tmp_path / ".owloop" / "specs"
    specs.mkdir(parents=True)
    spec = specs / "01-test.md"
    target = tmp_path / "api.py"
    target.write_text("def removed(): pass\n", encoding="utf-8")
    spec.write_text(
        "# Spec\n\n## Acceptance Criteria\n"
        f"- `grep removed {target.name}` → no output\n",
        encoding="utf-8",
    )

    passed, failed, failures = verification.run_acceptance_criteria(
        tmp_path, specs, "01-test.md"
    )

    assert passed == 0
    assert failed == 1
    assert len(failures) == 1


def test_run_gate_restores_excluded_tracked_files(tmp_path: Path) -> None:
    """Acceptance-criteria commands must not leave mutations in spec-excluded files."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo, check=True, capture_output=True,
    )

    (repo / "uv.lock").write_text("original\n", encoding="utf-8")
    (repo / "README.md").write_text("# test", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)

    specs = repo / ".owloop" / "specs"
    specs.mkdir(parents=True)
    spec = specs / "01-test.md"
    spec.write_text(
        "# Spec\n\n"
        "## Acceptance Criteria\n"
        "- `echo changed > uv.lock`\n\n"
        "## Exclusions\n"
        "- `uv.lock`\n",
        encoding="utf-8",
    )

    guard_before = verification.guarded_hash(repo, specs, "01-test.md")
    result = verification.run_gate(repo, specs, "01-test.md", guard_before)

    assert result.tampered is False
    assert result.passed is True
    assert (repo / "uv.lock").read_text(encoding="utf-8") == "original\n"
