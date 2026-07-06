"""Tests for agent adapters."""

from __future__ import annotations

import os
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


def test_claude_build_cmd_forwards_max_turns_when_supported() -> None:
    adapter = ClaudeCodeAdapter(model="claude-sonnet-5", max_turns=25)
    # Pretend the installed CLI advertises the flag.
    adapter._supported_flags_cache = {"--max-turns"}
    cmd = adapter._build_cmd()
    assert "--max-turns" in cmd
    assert cmd[cmd.index("--max-turns") + 1] == "25"


def test_claude_build_cmd_omits_max_turns_when_unsupported() -> None:
    adapter = ClaudeCodeAdapter(model="claude-sonnet-5", max_turns=25)
    # Older CLI: flag not present in --help. Degrade gracefully.
    adapter._supported_flags_cache = set()
    cmd = adapter._build_cmd()
    assert "--max-turns" not in cmd


def test_claude_build_cmd_no_limit_flags_by_default() -> None:
    adapter = ClaudeCodeAdapter(model="claude-sonnet-5")
    cmd = adapter._build_cmd()
    assert "--max-turns" not in cmd
    assert "--max-budget-usd" not in cmd


def test_claude_build_cmd_forwards_budget_when_supported() -> None:
    adapter = ClaudeCodeAdapter(model="claude-sonnet-5", max_budget_usd=1.5)
    adapter._supported_flags_cache = {"--max-budget-usd"}
    cmd = adapter._build_cmd()
    assert "--max-budget-usd" in cmd
    assert cmd[cmd.index("--max-budget-usd") + 1] == "1.5"


def test_claude_result_event_flags_native_limit() -> None:
    adapter = ClaudeCodeAdapter(model="claude-sonnet-5")
    adapter._limit_reached = False
    adapter._result_text_parts = []
    adapter.token_tracker.reset()
    adapter._parse_stream_event('{"type": "result", "subtype": "error_max_turns", "result": "hit limit"}')
    assert adapter._limit_reached is True


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
    # On Unix a dead process raises ProcessLookupError; on Windows os.kill
    # raises a generic OSError. OSError is the common base class.
    with pytest.raises(OSError):
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


class _ScriptedClaudeAdapter(ClaudeCodeAdapter):
    """`ClaudeCodeAdapter` whose `_build_cmd` runs a scripted fake CLI instead of `claude`."""

    def __init__(self, script: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._script = script

    def _build_cmd(self, prompt: str = "") -> list[str]:
        return [sys.executable, "-c", self._script]


class _ScriptedKimiAdapter(KimiCodeAdapter):
    """`KimiCodeAdapter` whose `_build_cmd` runs a scripted fake CLI instead of `kimi`."""

    def __init__(self, script: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._script = script

    def _build_cmd(self, prompt: str | None = None) -> list[str]:
        return [sys.executable, "-c", self._script]


def test_claude_adapter_updates_token_tracker_from_stream(tmp_path: Path) -> None:
    script = (
        "import json\n"
        "print(json.dumps({'type': 'result', 'result': 'done', "
        "'usage': {'input_tokens': 100, 'output_tokens': 50}, "
        "'total_cost_usd': 0.02}))\n"
    )
    adapter = _ScriptedClaudeAdapter(script, model="claude-sonnet-5")

    result = adapter.run("prompt", tmp_path)

    assert adapter.token_tracker.has_explicit_usage is True
    assert result.tokens_used == 150
    assert result.cost_usd == pytest.approx(0.02)


def test_kimi_adapter_extracts_usage_or_falls_back_to_heuristic(tmp_path: Path) -> None:
    script_with_usage = (
        "import json\n"
        "print(json.dumps({'role': 'assistant', 'content': 'working', "
        "'usage': {'prompt_tokens': 40, 'completion_tokens': 10}}))\n"
    )
    adapter = _ScriptedKimiAdapter(script_with_usage)

    result = adapter.run("prompt", tmp_path)

    assert adapter.token_tracker.has_explicit_usage is True
    assert result.tokens_used == 50

    script_without_usage = (
        "import json\n"
        "print(json.dumps({'role': 'assistant', 'content': 'Total tokens: 77'}))\n"
    )
    fallback_adapter = _ScriptedKimiAdapter(script_without_usage)

    fallback_result = fallback_adapter.run("prompt", tmp_path)

    assert fallback_adapter.token_tracker.has_explicit_usage is False
    assert fallback_result.tokens_used == 77
