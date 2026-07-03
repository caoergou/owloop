"""Agent adapter abstraction — decouples the engine from any one coding-agent CLI.

`OwloopEngine` only ever talks to an `AgentAdapter`. Today the only real
implementation is `ClaudeCodeAdapter` (shells out to `claude -p`), but the
interface leaves room for future adapters (Codex, OpenCode, ...) and for a
`MockAdapter` in tests without touching engine code.
"""

from __future__ import annotations

import contextlib
import os
import queue
import re
import shutil
import signal
import subprocess
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
DONE_SIGNAL_RE = re.compile(r"<promise>(?:ALL_)?DONE</promise>")

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


class ClaudeCodeAdapter(AgentAdapter):
    def __init__(
        self,
        model: str = "claude-sonnet-5",
        permission_mode: str = "auto",
        claude_cmd: str = "claude",
        idle_timeout: float = DEFAULT_IDLE_TIMEOUT,
    ) -> None:
        self.model = model
        self.permission_mode = permission_mode
        self.claude_cmd = claude_cmd
        self.idle_timeout = idle_timeout

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

    def _build_cmd(self) -> list[str]:
        return [
            self.claude_cmd,
            "-p",
            "--model",
            self.model,
            "--permission-mode",
            self.permission_mode,
        ]

    @staticmethod
    def _killpg(proc: subprocess.Popen) -> None:
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
        try:
            proc = subprocess.Popen(
                self._build_cmd(),
                cwd=cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
        except FileNotFoundError:
            return AgentResult(stdout="", returncode=127, success=False, has_completion_signal=False)

        assert proc.stdin is not None and proc.stdout is not None
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
        except BrokenPipeError:
            pass

        # Read stdout on a background thread so the main thread can enforce an
        # idle timeout (no output for N seconds → assume the agent is stuck).
        line_queue: queue.Queue[str | None] = queue.Queue()

        def _reader() -> None:
            try:
                for raw_line in proc.stdout:  # type: ignore[union-attr]
                    line_queue.put(strip_ansi(raw_line.rstrip("\n")))
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
                output_lines.append(line)
                if on_line:
                    on_line(line)

            if not timed_out:
                proc.wait()
        except KeyboardInterrupt:
            self._killpg(proc)
            raise

        clean_output = "\n".join(output_lines)
        match = None if timed_out else DONE_SIGNAL_RE.search(clean_output)
        returncode = -1 if timed_out else (proc.returncode if proc.returncode is not None else -1)

        return AgentResult(
            stdout=clean_output,
            returncode=returncode,
            success=(returncode == 0 and not timed_out),
            has_completion_signal=bool(match),
            done_signal=match.group(0) if match else None,
            timed_out=timed_out,
        )


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
            result = AgentResult(stdout="", returncode=0, success=True, has_completion_signal=False)
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
    idle_timeout: float = DEFAULT_IDLE_TIMEOUT,
) -> AgentAdapter:
    if agent == "claude":
        return ClaudeCodeAdapter(
            model=model,
            permission_mode=permission_mode,
            claude_cmd=claude_cmd,
            idle_timeout=idle_timeout,
        )
    raise ValueError(f"unknown agent type: {agent!r} (currently only supports 'claude')")
