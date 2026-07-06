"""AcpAdapter tests against the scripted fake ACP agent (see fake_acp_agent.py)."""

from __future__ import annotations

import sys
from pathlib import Path

from owloop.acp import AcpAdapter
from owloop.presets import AgentPreset

FAKE_AGENT = str(Path(__file__).parent / "fake_acp_agent.py")


def _preset(scenario: str = "happy", **kwargs) -> AgentPreset:
    return AgentPreset(
        key=f"fake-{scenario}",
        cmd=(sys.executable, FAKE_AGENT, scenario),
        **kwargs,
    )


def _run(scenario: str, tmp_path: Path, *, idle_timeout: float = 15.0, **preset_kwargs):
    adapter = AcpAdapter(_preset(scenario, **preset_kwargs), idle_timeout=idle_timeout)
    lines: list[str] = []
    result = adapter.run("do the work", cwd=tmp_path, on_line=lines.append)
    return result, lines


def test_happy_turn_succeeds_with_done_promise(tmp_path: Path) -> None:
    result, lines = _run("happy", tmp_path)

    assert result.success
    assert result.returncode == 0
    assert not result.timed_out
    assert result.promise_state == "DONE"
    assert result.has_completion_signal
    assert "Implemented the spec." in result.stdout


def test_happy_turn_streams_display_lines(tmp_path: Path) -> None:
    _result, lines = _run("happy", tmp_path)

    assert "[plan: 2 step(s)]" in lines
    assert "[execute: pytest -q]" in lines
    assert "Implemented the spec." in lines
    assert "All criteria pass." in lines


def test_happy_turn_records_usage_from_usage_update(tmp_path: Path) -> None:
    result, _lines = _run("happy", tmp_path)

    assert result.tokens_used == 1234
    assert result.cost_usd == 0.05


def test_permission_request_is_answered_with_allow_once(tmp_path: Path) -> None:
    # The fake agent only completes the turn when the client selects the
    # allow_once option — so success here proves the auto-answer policy.
    result, lines = _run("permission", tmp_path)

    assert result.success
    assert result.promise_state == "DONE"
    assert any(line.startswith("[permission: write src/app.py") for line in lines)


def test_refusal_stop_reason_is_not_success(tmp_path: Path) -> None:
    result, _lines = _run("refusal", tmp_path)

    assert not result.success
    assert result.returncode == 0  # turn completed; refusal is not a crash
    assert result.promise_state == ""
    assert "cannot continue" in result.stdout


def test_hanging_agent_times_out(tmp_path: Path) -> None:
    result, _lines = _run("hang", tmp_path, idle_timeout=1.0)

    assert result.timed_out
    assert not result.success
    assert result.returncode == -1


def test_crashing_agent_reports_failure_with_stderr_tail(tmp_path: Path) -> None:
    result, _lines = _run("crash", tmp_path)

    assert not result.success
    assert result.returncode == 3
    assert "simulated crash" in result.stdout


def test_missing_binary_returns_127(tmp_path: Path) -> None:
    preset = AgentPreset(key="missing", cmd=("owloop-no-such-binary-xyz",))
    result = AcpAdapter(preset).run("prompt", cwd=tmp_path)

    assert not result.success
    assert result.returncode == 127


def test_missing_env_var_fails_before_spawn(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OWLOOP_TEST_MISSING_KEY", raising=False)
    preset = _preset("happy", env={"API_KEY": "${OWLOOP_TEST_MISSING_KEY}"})
    result = AcpAdapter(preset).run("prompt", cwd=tmp_path)

    assert not result.success
    assert result.returncode == 1
    assert "OWLOOP_TEST_MISSING_KEY" in result.stdout


def test_preflight_reports_binary_and_env_issues(monkeypatch) -> None:
    monkeypatch.delenv("OWLOOP_TEST_MISSING_KEY", raising=False)
    preset = AgentPreset(
        key="broken",
        cmd=("owloop-no-such-binary-xyz",),
        env={"API_KEY": "${OWLOOP_TEST_MISSING_KEY}"},
    )
    issues = AcpAdapter(preset).preflight()

    assert len(issues) == 2
    assert "owloop-no-such-binary-xyz" in issues[0]
    assert "OWLOOP_TEST_MISSING_KEY" in issues[1]


def test_preflight_passes_for_working_preset() -> None:
    assert AcpAdapter(_preset("happy")).preflight() == []


def test_adapter_name_and_config_dirs() -> None:
    preset = _preset("happy", label="Fake Agent", default_model="fake-1", config_dirs=(".fake",))
    adapter = AcpAdapter(preset)

    assert adapter.name == "Fake Agent via ACP (fake-1)"
    assert adapter.config_dirs == (".fake",)
