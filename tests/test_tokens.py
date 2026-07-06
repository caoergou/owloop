"""Tests for token tracking and budget cap."""

import subprocess

import pytest

from owloop.adapters import AgentResult, MockAdapter
from owloop.engine import EngineConfig, OwloopEngine
from owloop.tokens import TokenTracker


def _make_repo(tmp_path):
    """Create a minimal git repo with a spec so the engine can start."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True, capture_output=True)
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    (specs_dir / "01-example.md").write_text(
        "# Spec: example\n\n## Priority: 1\n\n## Requirements\n- do thing\n\n"
        "## Acceptance Criteria\n- [ ] echo done\n\n## Exclusions\n- none\n\n"
        "Output when complete: `<promise>DONE</promise>`\n"
    )
    return tmp_path


def test_token_tracker_parses_input_output_json():
    tracker = TokenTracker()
    text = '{"usage": {"input_tokens": 1234, "output_tokens": 567}}'
    assert tracker.count_from_text(text) == 1801


def test_token_tracker_parses_total_tokens_line():
    tracker = TokenTracker()
    assert tracker.count_from_line("Total tokens: 999") == 999
    assert tracker.count_from_line("Used 42 tokens") == 42


def test_token_tracker_ignores_unrelated_lines():
    tracker = TokenTracker()
    assert tracker.count_from_line("this is just a log line") == 0


def test_token_tracker_sums_across_lines():
    tracker = TokenTracker()
    text = "Input tokens: 100\nOutput tokens: 50\nTotal tokens: 999"
    assert tracker.count_from_text(text) == 1149


def test_mock_adapter_passes_through_tokens(tmp_path):
    repo = _make_repo(tmp_path)
    adapter = MockAdapter(
        responses=[
            AgentResult(
                stdout="Total tokens: 1234",
                returncode=0,
                success=True,
                has_completion_signal=True,
                done_signal="<promise>DONE</promise>",
                tokens_used=1234,
            )
        ]
    )
    config = EngineConfig(project_dir=repo, max_tokens=2000, worktree=False)
    engine = OwloopEngine(config, adapter, on_event=None)
    engine.log_dir.mkdir(parents=True, exist_ok=True)
    engine._write_prompt_file()
    events = []
    engine.on_event = lambda kind, data: events.append((kind, data))
    result = engine.run_iteration(1)
    assert result.tokens_used == 1234
    assert engine.tokens_used == 1234
    assert any(kind == "tokens_update" for kind, _ in events)


def test_engine_kills_iteration_exceeding_per_iteration_cap(tmp_path):
    repo = _make_repo(tmp_path)
    adapter = MockAdapter(
        responses=[
            AgentResult(
                stdout="Total tokens: 5000",
                returncode=0,
                success=True,
                has_completion_signal=True,
                done_signal="<promise>DONE</promise>",
                tokens_used=5000,
            )
        ]
    )
    config = EngineConfig(project_dir=repo, max_tokens_per_iteration=1000, worktree=False)
    engine = OwloopEngine(config, adapter, on_event=None)
    engine.log_dir.mkdir(parents=True, exist_ok=True)
    engine._write_prompt_file()
    events = []
    engine.on_event = lambda kind, data: events.append((kind, data))

    result = engine.run_iteration(1)

    assert result.success is False
    assert result.promise_state != "DONE"
    assert any(kind == "iteration_token_limit_exceeded" for kind, _ in events)


def test_run_summary_includes_estimated_cost(tmp_path):
    repo = _make_repo(tmp_path)
    adapter = MockAdapter(
        responses=[
            AgentResult(
                stdout="Total tokens: 100",
                returncode=0,
                success=True,
                has_completion_signal=True,
                done_signal="<promise>DONE</promise>",
                tokens_used=100,
                cost_usd=0.05,
            ),
        ]
    )
    config = EngineConfig(project_dir=repo, worktree=False, max_iterations=1)
    engine = OwloopEngine(config, adapter)

    summary = engine.run()

    assert summary.estimated_cost_usd == pytest.approx(0.05)


def test_engine_stops_when_token_budget_reached(tmp_path):
    repo = _make_repo(tmp_path)
    adapter = MockAdapter(
        responses=[
            AgentResult(
                stdout="Total tokens: 800",
                returncode=0,
                success=True,
                has_completion_signal=False,
                tokens_used=800,
            ),
            AgentResult(
                stdout="Total tokens: 800",
                returncode=0,
                success=True,
                has_completion_signal=False,
                tokens_used=800,
            ),
        ]
    )
    config = EngineConfig(
        project_dir=repo,
        max_tokens=1000,
        worktree=False,
    )
    engine = OwloopEngine(config, adapter)
    events = []
    engine.on_event = lambda kind, data: events.append((kind, data))
    summary = engine.run()
    assert summary.stopped_reason == "max_tokens"
    assert summary.tokens_used == 1600
    assert any(kind == "max_tokens_reached" for kind, _ in events)
