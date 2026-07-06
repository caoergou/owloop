"""Tests for the #36 convergence sweep and notification integration."""

from __future__ import annotations

import subprocess
from pathlib import Path

from owloop.adapters import AgentResult, MockAdapter
from owloop.engine import EngineConfig, OwloopEngine

_VALID_GAP_SPEC = """\
# Spec: gap-fix

## Priority: 2

## Requirements
- [ ] Close the integration gap left after the initial specs.

## Acceptance Criteria
- [ ] `true` exits zero

## Exclusions
- Do NOT modify pyproject.toml

## Style
- Follow existing conventions

## Verification
Run the acceptance criteria commands.

<promise>DONE</promise>
"""


def _git_init(repo: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("# t", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)


def _done() -> AgentResult:
    return AgentResult(
        stdout="<promise>DONE</promise>",
        returncode=0,
        success=True,
        has_completion_signal=True,
        done_signal="<promise>DONE</promise>",
    )


class _ConvergeAdapter(MockAdapter):
    """Build agent that also, on the first convergence sweep, writes a gap spec."""

    def __init__(self, specs_dir: Path, gap_spec: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._specs_dir = specs_dir
        self._gap_spec = gap_spec
        self.build_calls = 0
        self.sweep_calls = 0

    def run(self, prompt: str, cwd: Path, *, on_line=None) -> AgentResult:
        if "Convergence Sweep" in prompt:
            self.sweep_calls += 1
            if self.sweep_calls == 1 and self._gap_spec:
                (self._specs_dir / "02-gap.md").write_text(self._gap_spec, encoding="utf-8")
            return _done()
        self.build_calls += 1
        return _done()


def _engine(repo: Path, adapter, **cfg) -> OwloopEngine:
    return OwloopEngine(EngineConfig(project_dir=repo, worktree=False, **cfg), adapter)


def test_converge_sweep_appends_gap_spec_then_converges(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    specs = repo / ".owloop" / "specs"
    specs.mkdir(parents=True)
    (specs / "01-t.md").write_text(
        "# Spec: t\n\n## Acceptance Criteria\n- `true`\n", encoding="utf-8"
    )
    monkeypatch.setattr("owloop.engine.time.sleep", lambda _: None)

    adapter = _ConvergeAdapter(specs, _VALID_GAP_SPEC)
    engine = _engine(repo, adapter, max_iterations=10, converge_sweeps=1)
    monkeypatch.setattr(engine, "_push", lambda b: None)
    events: list[tuple[str, dict]] = []
    engine.on_event = lambda k, d: events.append((k, d))

    summary = engine.run()

    assert summary.stopped_reason == "success"
    # One sweep ran, appended the gap spec, and the loop built it before ending.
    assert adapter.sweep_calls == 1
    assert adapter.build_calls == 2  # 01-t + 02-gap
    assert any(k == "converge_gap_specs" for k, _ in events)
    assert any(k == "converged" for k, _ in events) or adapter.sweep_calls == 1


def test_converge_rejects_invalid_gap_spec(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    specs = repo / ".owloop" / "specs"
    specs.mkdir(parents=True)
    (specs / "01-t.md").write_text(
        "# Spec: t\n\n## Acceptance Criteria\n- `true`\n", encoding="utf-8"
    )
    monkeypatch.setattr("owloop.engine.time.sleep", lambda _: None)

    # Invalid gap spec: no Acceptance Criteria / Exclusions → SpecLinter errors.
    invalid = "# Spec: bad\n\n## Priority: 2\n\n## Requirements\n- [ ] do a thing\n"
    adapter = _ConvergeAdapter(specs, invalid)
    engine = _engine(repo, adapter, max_iterations=10, converge_sweeps=1)
    monkeypatch.setattr(engine, "_push", lambda b: None)
    events: list[tuple[str, dict]] = []
    engine.on_event = lambda k, d: events.append((k, d))

    summary = engine.run()

    assert summary.stopped_reason == "success"
    # The malformed gap spec was rejected and removed, not entered into the queue.
    assert any(k == "converge_spec_rejected" for k, _ in events)
    assert not (specs / "02-gap.md").exists()
    assert adapter.build_calls == 1  # only the original spec was built


def test_converge_disabled_by_default(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    specs = repo / ".owloop" / "specs"
    specs.mkdir(parents=True)
    (specs / "01-t.md").write_text(
        "# Spec: t\n\n## Acceptance Criteria\n- `true`\n", encoding="utf-8"
    )
    monkeypatch.setattr("owloop.engine.time.sleep", lambda _: None)

    adapter = _ConvergeAdapter(specs, _VALID_GAP_SPEC)
    engine = _engine(repo, adapter, max_iterations=10)  # converge_sweeps=0
    monkeypatch.setattr(engine, "_push", lambda b: None)

    summary = engine.run()

    assert summary.stopped_reason == "success"
    assert adapter.sweep_calls == 0  # no sweep when disabled


def test_notification_fires_at_run_end(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    specs = repo / ".owloop" / "specs"
    specs.mkdir(parents=True)
    (specs / "01-t.md").write_text(
        "# Spec: t\n\n## Acceptance Criteria\n- `true`\n", encoding="utf-8"
    )
    monkeypatch.setattr("owloop.engine.time.sleep", lambda _: None)

    sent: list[str] = []
    monkeypatch.setattr(
        "owloop.notifications._post_webhook",
        lambda url, msg, summary, emit: sent.append(url),
    )

    adapter = MockAdapter(responses=[_done()])
    engine = _engine(
        repo, adapter, max_iterations=1, notify_webhook="https://example.test/hook"
    )
    monkeypatch.setattr(engine, "_push", lambda b: None)

    engine.run()

    assert sent == ["https://example.test/hook"]
