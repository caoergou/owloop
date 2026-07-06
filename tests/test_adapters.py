"""Tests for agent adapters."""

from __future__ import annotations

from pathlib import Path

import pytest

from owloop.adapters import (
    AgentResult,
    ClaudeCodeAdapter,
    KimiCodeAdapter,
    MockAdapter,
    get_adapter,
)


def test_get_adapter_returns_claude_adapter() -> None:
    adapter = get_adapter("claude", model="claude-sonnet-5")
    assert isinstance(adapter, ClaudeCodeAdapter)
    assert "Claude Code" in adapter.name


def test_get_adapter_returns_kimi_adapter() -> None:
    adapter = get_adapter("kimi", model="kimi-code/kimi-for-coding")
    assert isinstance(adapter, KimiCodeAdapter)
    assert "Kimi Code CLI" in adapter.name


def test_get_adapter_unknown_agent_raises() -> None:
    with pytest.raises(ValueError, match="unknown agent type"):
        get_adapter("unknown", model="test")


def test_mock_adapter_records_calls_and_returns_defaults() -> None:
    adapter = MockAdapter()
    cwd = Path("/tmp/fake")
    result = adapter.run("prompt", cwd)

    assert adapter.calls == [("prompt", cwd)]
    assert result.success is True
    assert result.returncode == 0


def test_mock_adapter_uses_provided_responses() -> None:
    adapter = MockAdapter(responses=[
        AgentResult(
            stdout="done",
            returncode=0,
            success=True,
            has_completion_signal=True,
            done_signal="<promise>DONE</promise>",
        ),
    ])
    result = adapter.run("prompt", Path("/tmp"))
    assert result.stdout == "done"
    assert result.has_completion_signal is True


def test_mock_adapter_preflight_issues() -> None:
    adapter = MockAdapter(preflight_issues=["missing tool"])
    assert adapter.preflight() == ["missing tool"]


def test_claude_code_adapter_build_cmd() -> None:
    adapter = ClaudeCodeAdapter(model="claude-sonnet-5", permission_mode="auto")
    cmd = adapter._build_cmd()
    assert cmd[0] == "claude"
    assert "-p" in cmd
    assert "--permission-mode" in cmd
    assert "auto" in cmd
    assert "--output-format" in cmd
    assert "stream-json" in cmd


def test_kimi_code_adapter_build_cmd() -> None:
    adapter = KimiCodeAdapter(model="kimi-code/kimi-for-coding")
    cmd = adapter._build_cmd()
    assert cmd[0] == "kimi"
    assert "--output-format" in cmd
    assert "stream-json" in cmd
    # Kimi does not accept --auto or --yolo together with --prompt
    assert "--auto" not in cmd
    assert "--yolo" not in cmd


def test_kimi_code_adapter_build_cmd_with_prompt() -> None:
    adapter = KimiCodeAdapter(model="kimi-code/kimi-for-coding")
    cmd = adapter._build_cmd(prompt="do something")
    assert cmd[0] == "kimi"
    assert "--prompt" in cmd
    assert "do something" in cmd
    assert "--output-format" in cmd
    assert "stream-json" in cmd


def test_kimi_code_adapter_custom_cmd() -> None:
    adapter = KimiCodeAdapter(kimi_cmd="/path/to/kimi")
    assert adapter._build_cmd()[0] == "/path/to/kimi"
