"""Tests for agent adapters."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

import pytest

from owloop.adapters import (
    AgentResult,
    ClaudeCodeAdapter,
    KimiCodeAdapter,
    MockAdapter,
    StreamingAgentAdapter,
    get_adapter,
)
from owloop.tokens import TokenTracker


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


class _EchoAdapter(StreamingAgentAdapter):
    """Minimal concrete `StreamingAgentAdapter` for exercising the base class.

    `_parse_stream_event` echoes each raw stdout line verbatim and feeds it
    into `_result_text_parts`, so the resulting `AgentResult.stdout` is just
    the process's raw stdout with whitespace-only lines dropped.
    """

    def __init__(self, idle_timeout: float = 5.0) -> None:
        self.idle_timeout = idle_timeout
        self.token_tracker = TokenTracker()
        self.cmd: list[str] = [sys.executable, "-c", "pass"]

    @property
    def name(self) -> str:
        return "Echo"

    def preflight(self) -> list[str]:
        return []

    def _build_cmd(self, prompt: str = "") -> list[str]:
        return self.cmd

    def _parse_stream_event(self, raw: str) -> str | None:
        raw = raw.strip()
        if not raw:
            return None
        self._result_text_parts.append(raw)
        return raw


class _ArgvPromptAdapter(_EchoAdapter):
    """Like `_EchoAdapter` but passes the prompt via argv instead of stdin."""

    _write_prompt_to_stdin = False

    def _build_cmd(self, prompt: str = "") -> list[str]:
        return [*self.cmd, prompt]


def test_streaming_adapter_normal_stream_completion(tmp_path: Path) -> None:
    adapter = _EchoAdapter()
    adapter.cmd = [sys.executable, "-c", "print('hello'); print('world')"]

    lines: list[str] = []
    result = adapter.run("prompt", tmp_path, on_line=lines.append)

    assert result.success is True
    assert result.timed_out is False
    assert result.returncode == 0
    assert lines == ["hello", "world"]
    assert result.stdout == "hello\nworld"


def test_streaming_adapter_promise_signal_extraction(tmp_path: Path) -> None:
    adapter = _EchoAdapter()
    adapter.cmd = [sys.executable, "-c", "print('<promise>DONE</promise>')"]

    result = adapter.run("prompt", tmp_path)

    assert result.has_completion_signal is True
    assert result.done_signal == "<promise>DONE</promise>"
    assert result.promise_state == "DONE"


def test_streaming_adapter_idle_timeout_kills_process(tmp_path: Path) -> None:
    script = "import os, time\nprint(os.getpid(), flush=True)\ntime.sleep(30)\n"
    adapter = _EchoAdapter(idle_timeout=0.3)
    adapter.cmd = [sys.executable, "-c", script]

    result = adapter.run("prompt", tmp_path)

    assert result.timed_out is True
    assert result.success is False
    assert result.returncode == -1

    pid = int(result.stdout.strip())
    if platform.system() == "Windows":
        # `os.kill(pid, 0)` is unreliable on Windows; use tasklist instead.
        proc = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert str(pid) not in proc.stdout
    else:
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)


def test_streaming_adapter_writes_prompt_to_stdin_by_default(tmp_path: Path) -> None:
    adapter = _EchoAdapter()
    adapter.cmd = [sys.executable, "-c", "import sys; print(len(sys.stdin.read()), flush=True)"]

    result = adapter.run("hello world", tmp_path)

    assert result.stdout.strip() == str(len("hello world"))


def test_streaming_adapter_skips_stdin_when_disabled(tmp_path: Path) -> None:
    adapter = _ArgvPromptAdapter()
    adapter.cmd = [sys.executable, "-c", "import sys; print(sys.argv[1], flush=True)"]

    result = adapter.run("hello world", tmp_path)

    assert result.stdout.strip() == "hello world"


def test_streaming_adapter_missing_binary_returns_failure(tmp_path: Path) -> None:
    adapter = _EchoAdapter()
    adapter.cmd = ["/definitely/not/a/real/binary-xyz"]

    result = adapter.run("prompt", tmp_path)

    assert result.returncode == 127
    assert result.success is False
    assert result.has_completion_signal is False
