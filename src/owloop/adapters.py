"""Agent adapter abstraction — decouples the engine from any one coding-agent CLI.

`OwloopEngine` only ever talks to an `AgentAdapter`. Today the real
implementations are `ClaudeCodeAdapter` (shells out to `claude -p`) and
`KimiCodeAdapter` (shells out to `kimi --prompt`), with `MockAdapter` for
tests.
"""

from __future__ import annotations

import contextlib
import json
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from owloop.promise import PROMISE_SIGNAL_RE, parse_promise_signal
from owloop.tokens import TokenTracker

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

DEFAULT_IDLE_TIMEOUT = 3600  # 60 minutes — claude -p buffers all output until
# the end of a turn, so "no output" ≠ "stuck". Real-test showed spec 01 took
# 18 minutes with zero intermediate output. 60min gives headroom for large specs.

OnLine = Callable[[str], None]


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


@dataclass
class AgentResult:
    stdout: str
    returncode: int
    success: bool  # returncode == 0 and not timed_out
    has_completion_signal: bool
    done_signal: str | None = None
    timed_out: bool = False
    tokens_used: int = 0
    promise_state: str = ""  # "DONE" | "BLOCKED" | "DECIDE" | ""
    promise_payload: str = ""  # text after the colon for BLOCKED/DECIDE


class AgentAdapter(ABC):
    @abstractmethod
    def run(self, prompt: str, cwd: Path, *, on_line: OnLine | None = None) -> AgentResult:
        """Run one iteration against `prompt`, streaming output lines via `on_line`."""
        ...

    @abstractmethod
    def preflight(self) -> list[str]:
        """Return a list of blocking problems; empty list means all checks passed."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...


class StreamingAgentAdapter(AgentAdapter):
    """Base class for CLI agents that stream JSON events over a subprocess.

    Owns the subprocess lifecycle, the stdout reader thread, queue-based line
    streaming, promise-signal extraction, the token-counting fallback, and
    idle-timeout/process-cleanup handling. Concrete adapters only need to
    supply `_build_cmd` (how to invoke the CLI) and `_parse_stream_event`
    (how to turn one raw stdout line into on_line-displayable text).
    """

    idle_timeout: float
    token_tracker: TokenTracker

    # Claude receives its prompt via stdin; Kimi receives it as a `--prompt`
    # CLI arg. Adapters that pass the prompt through argv should set this to
    # False so `run()` never opens/writes a stdin pipe — writing to a pipe
    # the child never reads can deadlock once the prompt exceeds the OS pipe
    # buffer.
    _write_prompt_to_stdin: bool = True

    @abstractmethod
    def _build_cmd(self, prompt: str = "") -> list[str]:
        """Return the argv for invoking the underlying CLI with this prompt."""
        ...

    @abstractmethod
    def _parse_stream_event(self, raw: str) -> str | None:
        """Parse one raw stdout line into on_line-displayable text, or None.

        Implementations may append fragments to `self._result_text_parts` to
        build the "clean" final transcript used for promise-signal extraction
        and token counting — this can differ from the returned display text
        (e.g. Claude's terminal `result` event replaces the whole transcript
        with a single summary).
        """
        ...

    @staticmethod
    def _killpg(proc: subprocess.Popen) -> None:
        """Terminate the agent process (and its group when possible)."""
        if sys.platform == "win32":
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            return

        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)

    def run(self, prompt: str, cwd: Path, *, on_line: OnLine | None = None) -> AgentResult:
        self._result_text_parts: list[str] = []

        popen_kwargs: dict = {
            "cwd": cwd,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "bufsize": 1,
        }
        if self._write_prompt_to_stdin:
            popen_kwargs["stdin"] = subprocess.PIPE
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        try:
            proc = subprocess.Popen(self._build_cmd(prompt), **popen_kwargs)
        except FileNotFoundError:
            return AgentResult(
                stdout="",
                returncode=127,
                success=False,
                has_completion_signal=False,
                promise_state="",
                promise_payload="",
            )

        if self._write_prompt_to_stdin:
            assert proc.stdin is not None
            try:
                proc.stdin.write(prompt)
                proc.stdin.close()
            except BrokenPipeError:
                pass

        assert proc.stdout is not None

        line_queue: queue.Queue[str | None] = queue.Queue()

        def _reader() -> None:
            try:
                for raw_line in proc.stdout:  # type: ignore[union-attr]
                    text = self._parse_stream_event(raw_line)
                    if text:
                        for sub_line in text.splitlines():
                            if sub_line.strip():
                                line_queue.put(sub_line)
            finally:
                line_queue.put(None)

        reader_thread = threading.Thread(target=_reader, daemon=True)
        reader_thread.start()

        output_lines: list[str] = []
        timed_out = False

        try:
            while True:
                try:
                    line = line_queue.get(timeout=self.idle_timeout)
                except queue.Empty:
                    timed_out = True
                    self._killpg(proc)
                    break
                if line is None:
                    break
                if line:
                    output_lines.append(line)
                    if on_line:
                        on_line(line)

            if not timed_out:
                proc.wait()
        except KeyboardInterrupt:
            self._killpg(proc)
            raise

        clean_output = "\n".join(self._result_text_parts) if self._result_text_parts else "\n".join(output_lines)
        match = None if timed_out else PROMISE_SIGNAL_RE.search(clean_output)
        parsed = parse_promise_signal(clean_output) if match else None
        returncode = -1 if timed_out else (proc.returncode if proc.returncode is not None else -1)
        tokens_used = self.token_tracker.count_from_text(clean_output)

        return AgentResult(
            stdout=clean_output,
            returncode=returncode,
            success=(returncode == 0 and not timed_out),
            has_completion_signal=bool(match),
            done_signal=match.group(0) if match else None,
            timed_out=timed_out,
            tokens_used=tokens_used,
            promise_state=parsed[0] if parsed else "",
            promise_payload=parsed[1] if parsed else "",
        )


class ClaudeCodeAdapter(StreamingAgentAdapter):
    def __init__(
        self,
        model: str = "claude-sonnet-5",
        permission_mode: str = "auto",
        claude_cmd: str = "claude",
        idle_timeout: float = DEFAULT_IDLE_TIMEOUT,
        token_tracker: TokenTracker | None = None,
    ) -> None:
        self.model = model
        self.permission_mode = permission_mode
        self.claude_cmd = claude_cmd
        self.idle_timeout = idle_timeout
        self.token_tracker = token_tracker or TokenTracker()

    @property
    def name(self) -> str:
        return f"Claude Code ({self.model})"

    def preflight(self) -> list[str]:
        issues: list[str] = []

        if not shutil.which(self.claude_cmd):
            issues.append(f"{self.claude_cmd} command not found, please install and log in to Claude Code CLI")
            return issues

        try:
            # Feed the smoke-test prompt via stdin (like real iterations do,
            # see run() below) rather than as a CLI arg — subprocess.run's
            # `input=` writes it and closes stdin immediately, so the child
            # can never block waiting on stdin (e.g. when run under a real
            # interactive terminal where stdin has no natural EOF).
            probe = subprocess.run(
                self._build_cmd(),
                input="respond with just ok",
                capture_output=True,
                text=True,
                timeout=30,
            )
            if probe.returncode != 0:
                detail = (probe.stderr or probe.stdout).strip().splitlines()
                tail = detail[-1] if detail else "(no output)"
                issues.append(f"claude smoke test failed (returncode={probe.returncode}): {tail}")
        except subprocess.TimeoutExpired:
            issues.append("claude smoke test timed out (30s), please check network connection or login status")
        except OSError as exc:
            issues.append(f"claude smoke test error: {exc}")

        return issues

    def _build_cmd(self, prompt: str = "") -> list[str]:
        return [
            self.claude_cmd,
            "-p",
            "--model",
            self.model,
            "--permission-mode",
            self.permission_mode,
            "--output-format",
            "stream-json",
        ]

    def _parse_stream_event(self, raw: str) -> str | None:
        """Parse a stream-json line and return displayable text, or None."""
        raw = raw.strip()
        if not raw:
            return None
        try:
            event = json.loads(raw)
        except (ValueError, TypeError):
            return None

        etype = event.get("type", "")

        if etype == "assistant":
            msg = event.get("message", {})
            parts = []
            for block in msg.get("content", []):
                if block.get("type") == "text":
                    text = block.get("text", "").strip()
                    if text and len(text) > 1:
                        parts.append(text)
                        if "<promise>" not in text:
                            self._result_text_parts.append(text)
                elif block.get("type") == "tool_use":
                    name = block.get("name", "")
                    inp = block.get("input", {})
                    if name == "Read":
                        parts.append(f"[reading {inp.get('file_path', '?')}]")
                    elif name == "Write":
                        parts.append(f"[writing {inp.get('file_path', '?')}]")
                    elif name == "Edit":
                        parts.append(f"[editing {inp.get('file_path', '?')}]")
                    elif name in ("Bash", "bash"):
                        cmd = inp.get("command", "")
                        cmd = cmd.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
                        cmd = " ".join(cmd.split()).strip()
                        if len(cmd) > 100:
                            cmd = cmd[:97] + "..."
                        parts.append(f"[running: {cmd}]")
                    elif name in ("Grep", "Glob", "LSP"):
                        parts.append(f"[{name.lower()}: {str(inp.get('pattern', inp.get('query', '')))[:60]}]")
            return "\n".join(parts) if parts else None

        if etype == "tool_result":
            content = event.get("content", "")
            if isinstance(content, str) and content.strip():
                lines = content.strip().splitlines()
                if len(lines) <= 3:
                    return content.strip()
                return f"{lines[0]}\n... ({len(lines)} lines)\n{lines[-1]}"
            return None

        if etype == "result":
            text = event.get("result", "")
            if text:
                self._result_text_parts.clear()
                self._result_text_parts.append(text)
            usage = event.get("usage", {})
            cost = event.get("total_cost_usd", 0)
            in_tok = usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
            out_tok = usage.get("output_tokens", 0)
            model_usage = event.get("modelUsage", {})
            model_name = next(iter(model_usage), "")
            parts = []
            if in_tok or out_tok:
                parts.append(f"{in_tok + out_tok:,} tokens ({in_tok:,} in + {out_tok:,} out)")
            if cost:
                parts.append(f"${cost:.4f}")
            if model_name:
                parts.append(model_name)
            if parts:
                return f"[usage: {' · '.join(parts)}]"
            return None

        return None


class KimiCodeAdapter(StreamingAgentAdapter):
    """Adapter for Kimi Code CLI (`kimi --prompt`).

    Kimi's non-interactive prompt mode uses `--prompt` and `--output-format
    stream-json`. Notably, `--prompt` cannot be combined with `--auto` or
    `--yolo`; the permission mode is taken from the user's Kimi config
    (`default_permission_mode`). For owloop this should be set to `"auto"`.
    """

    _write_prompt_to_stdin = False

    def __init__(
        self,
        model: str = "kimi-code/kimi-for-coding",
        permission_mode: str = "auto",
        kimi_cmd: str = "kimi",
        idle_timeout: float = DEFAULT_IDLE_TIMEOUT,
        token_tracker: TokenTracker | None = None,
    ) -> None:
        self.model = model
        self.permission_mode = permission_mode
        self.kimi_cmd = kimi_cmd
        self.idle_timeout = idle_timeout
        self.token_tracker = token_tracker or TokenTracker()

    @property
    def name(self) -> str:
        return f"Kimi Code CLI ({self.model})"

    def preflight(self) -> list[str]:
        issues: list[str] = []

        if not shutil.which(self.kimi_cmd):
            issues.append(f"{self.kimi_cmd} command not found, please install Kimi Code CLI")
            return issues

        try:
            probe = subprocess.run(
                self._build_cmd(prompt="respond with just ok"),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if probe.returncode != 0:
                detail = (probe.stderr or probe.stdout).strip().splitlines()
                tail = detail[-1] if detail else "(no output)"
                issues.append(f"kimi smoke test failed (returncode={probe.returncode}): {tail}")
        except subprocess.TimeoutExpired:
            issues.append("kimi smoke test timed out (30s), please check network connection or login status")
        except OSError as exc:
            issues.append(f"kimi smoke test error: {exc}")

        return issues

    def _build_cmd(self, prompt: str | None = None) -> list[str]:
        # `--auto` and `--yolo` are interactive-mode flags and cannot be
        # combined with `--prompt`. The effective permission mode is controlled
        # by `default_permission_mode` in the user's Kimi config.
        cmd = [
            self.kimi_cmd,
            "--output-format",
            "stream-json",
        ]
        if prompt is not None:
            cmd.extend(["--prompt", prompt])
        return cmd

    def _parse_stream_event(self, raw: str) -> str | None:
        """Parse a Kimi stream-json line and return displayable text, or None."""
        raw = raw.strip()
        if not raw:
            return None

        try:
            event = json.loads(raw)
        except (ValueError, TypeError):
            # Kimi sometimes emits raw tool output before the JSON framing.
            # Surface it as-is so the user can see what happened.
            stripped = raw.strip()
            if stripped:
                return stripped
            return None

        role = event.get("role", "")

        if role == "assistant":
            content = event.get("content", "")
            if content and isinstance(content, str):
                text = content.strip()
                if text:
                    self._result_text_parts.append(text)
                    return text

            tool_calls = event.get("tool_calls", [])
            if tool_calls:
                summaries = []
                for call in tool_calls:
                    func = call.get("function", {}) if isinstance(call, dict) else {}
                    name = func.get("name", "") if isinstance(func, dict) else ""
                    args = func.get("arguments", "") if isinstance(func, dict) else ""
                    if name == "Bash":
                        try:
                            parsed_args = json.loads(args)
                            cmd = parsed_args.get("command", "")
                        except (ValueError, TypeError):
                            cmd = str(args)
                        cmd = cmd.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
                        cmd = " ".join(cmd.split()).strip()
                        if len(cmd) > 100:
                            cmd = cmd[:97] + "..."
                        summaries.append(f"[running: {cmd}]")
                    elif name:
                        summaries.append(f"[{name.lower()}]")
                return "\n".join(summaries) if summaries else None

        if role == "tool":
            content = event.get("content", "")
            if content and isinstance(content, str):
                text = content.strip()
                if text and "<promise>" in text:
                    self._result_text_parts.append(text)
                return None  # tool results are verbose; keep them out of the live stream

        if role == "meta":
            # session.resume_hint and similar metadata; not user-facing
            return None

        return None


class MockAdapter(AgentAdapter):
    """Scripted adapter for tests — no subprocess, no network."""

    def __init__(self, responses: list[AgentResult] | None = None, preflight_issues: list[str] | None = None):
        self._responses = list(responses or [])
        self._preflight_issues = preflight_issues or []
        self.calls: list[tuple[str, Path]] = []

    @property
    def name(self) -> str:
        return "Mock"

    def preflight(self) -> list[str]:
        return list(self._preflight_issues)

    def run(self, prompt: str, cwd: Path, *, on_line: OnLine | None = None) -> AgentResult:
        self.calls.append((prompt, cwd))
        if self._responses:
            result = self._responses.pop(0)
        else:
            result = AgentResult(
                stdout="",
                returncode=0,
                success=True,
                has_completion_signal=False,
                promise_state="",
                promise_payload="",
            )
        if not result.promise_state:
            parsed = parse_promise_signal(result.stdout)
            if parsed:
                result.promise_state = parsed[0]
                result.promise_payload = parsed[1]
        if on_line:
            for line in result.stdout.splitlines():
                on_line(line)
        return result


def get_adapter(
    agent: str,
    *,
    model: str,
    permission_mode: str = "auto",
    claude_cmd: str = "claude",
    kimi_cmd: str = "kimi",
    idle_timeout: float = DEFAULT_IDLE_TIMEOUT,
    token_tracker: TokenTracker | None = None,
) -> AgentAdapter:
    if agent == "claude":
        return ClaudeCodeAdapter(
            model=model,
            permission_mode=permission_mode,
            claude_cmd=claude_cmd,
            idle_timeout=idle_timeout,
            token_tracker=token_tracker,
        )
    if agent == "kimi":
        return KimiCodeAdapter(
            model=model,
            permission_mode=permission_mode,
            kimi_cmd=kimi_cmd,
            idle_timeout=idle_timeout,
            token_tracker=token_tracker,
        )
    raise ValueError(f"unknown agent type: {agent!r} (currently only supports 'claude', 'kimi')")
