"""ACP (Agent Client Protocol) adapter — one implementation, many agents.

Speaks JSON-RPC 2.0 over stdio (https://agentclientprotocol.com) to any
ACP-capable coding agent: spawn the agent subprocess, ``initialize``, open a
session with ``session/new``, run one full turn with ``session/prompt``, and
stream ``session/update`` notifications into owloop's ``on_line`` display.

Deliberately hand-rolled rather than depending on the ``agent-client-protocol``
SDK: owloop's adapter interface is synchronous, the protocol subset a loop
client needs is small, and the project's zero-extra-deps principle applies.

Fresh context per iteration is preserved: every ``run()`` spawns a new agent
process, opens a new session, runs exactly one prompt turn, and tears the
process down.

Permissions: the agent asks via ``session/request_permission``; owloop answers
programmatically, preferring ``allow_once`` — the spec explicitly permits
clients to answer automatically. This keeps the "Auto Mode, not YOLO" premise:
the agent is never launched in a bypass/YOLO mode; every request is granted
one-at-a-time by the harness (a future policy hook can deny by pattern).
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
from collections import deque
from pathlib import Path
from typing import Any

from owloop.adapters import (
    DEFAULT_IDLE_TIMEOUT,
    AgentAdapter,
    AgentResult,
    OnLine,
    terminate_process,
)
from owloop.presets import AgentPreset, MissingEnvError
from owloop.promise import PROMISE_SIGNAL_RE, parse_promise_signal
from owloop.tokens import IterationTokenLimitExceededError, TokenTracker

PROTOCOL_VERSION = 1

# Ranking for permission options: prefer the narrowest grant. Rejections are
# last resorts, used only when the agent offers nothing else.
_OPTION_KIND_RANK = {
    "allow_once": 0,
    "allow_always": 1,
    "reject_once": 2,
    "reject_always": 3,
}

_STDERR_TAIL_LINES = 30


class _AgentExitedError(Exception):
    """The agent process closed stdout before answering the pending request."""


class AcpAdapter(AgentAdapter):
    """Drive any ACP-capable agent CLI described by an :class:`AgentPreset`."""

    def __init__(
        self,
        preset: AgentPreset,
        *,
        model: str | None = None,
        idle_timeout: float = DEFAULT_IDLE_TIMEOUT,
        token_tracker: TokenTracker | None = None,
    ) -> None:
        self.preset = preset
        self.model = model or preset.default_model
        self.idle_timeout = idle_timeout
        self.token_tracker = token_tracker or TokenTracker()
        # Consumed by OwloopEngine.setup_worktree() when copying project config.
        self.config_dirs = preset.config_dirs

    @property
    def name(self) -> str:
        label = self.preset.display_label()
        return f"{label} via ACP ({self.model})" if self.model else f"{label} via ACP"

    def preflight(self) -> list[str]:
        issues: list[str] = []
        binary = self.preset.cmd[0]
        if not shutil.which(binary):
            issues.append(
                f"{binary} command not found — required to launch agent {self.preset.key!r}"
            )
        try:
            self.preset.resolve_env(self.model)
        except MissingEnvError as exc:
            issues.append(str(exc))
        return issues

    # ------------------------------------------------------------------ run

    def run(self, prompt: str, cwd: Path, *, on_line: OnLine | None = None) -> AgentResult:
        self._on_line = on_line
        self._result_text_parts: list[str] = []
        self._display_buf = ""
        self._latest_usage: dict[str, Any] = {}
        self._next_id = 0
        self._write_lock = threading.Lock()
        self.token_tracker.reset()

        try:
            env = {**os.environ, **self.preset.resolve_env(self.model)}
        except MissingEnvError as exc:
            return self._failure(str(exc), returncode=1)

        popen_kwargs: dict[str, Any] = {
            "cwd": cwd,
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "bufsize": 1,
            "env": env,
        }
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        try:
            proc = subprocess.Popen(list(self.preset.cmd), **popen_kwargs)
        except FileNotFoundError:
            return self._failure(f"{self.preset.cmd[0]}: command not found", returncode=127)

        self._proc = proc
        self._queue: queue.Queue[dict[str, Any] | None] = queue.Queue()
        stderr_tail: deque[str] = deque(maxlen=_STDERR_TAIL_LINES)

        threading.Thread(target=self._read_stdout, args=(proc,), daemon=True).start()
        threading.Thread(
            target=self._drain_stderr, args=(proc, stderr_tail), daemon=True
        ).start()

        timed_out = False
        stop_reason: str | None = None
        try:
            self._request(
                "initialize",
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "clientCapabilities": {
                        "fs": {"readTextFile": False, "writeTextFile": False}
                    },
                    "clientInfo": {"name": "owloop", "version": _owloop_version()},
                },
            )
            session = self._request(
                "session/new", {"cwd": str(Path(cwd).resolve()), "mcpServers": []}
            )
            session_id = session.get("sessionId", "")
            turn = self._request(
                "session/prompt",
                {
                    "sessionId": session_id,
                    "prompt": [{"type": "text", "text": prompt}],
                },
            )
            stop_reason = turn.get("stopReason")
        except TimeoutError:
            timed_out = True
            terminate_process(proc)
        except _AgentExitedError:
            proc.wait()
        except (KeyboardInterrupt, IterationTokenLimitExceededError):
            terminate_process(proc)
            raise
        except (BrokenPipeError, OSError):
            terminate_process(proc)
        finally:
            self._flush_display(final=True)

        if stop_reason is not None:
            # Turn finished cleanly; the process itself is just a transport,
            # so shut it down and report the turn outcome, not the exit code.
            self._shutdown(proc)
            returncode = 0
        else:
            terminate_process(proc)
            returncode = -1 if timed_out else (proc.returncode if proc.returncode is not None else -1)

        clean_output = "\n".join(self._result_text_parts)
        if stop_reason is None and not clean_output and stderr_tail:
            clean_output = "\n".join(stderr_tail)

        self._record_usage()
        match = None if timed_out else PROMISE_SIGNAL_RE.search(clean_output)
        parsed = parse_promise_signal(clean_output) if match else None

        return AgentResult(
            stdout=clean_output,
            returncode=returncode,
            success=(stop_reason == "end_turn"),
            has_completion_signal=bool(match),
            done_signal=match.group(0) if match else None,
            timed_out=timed_out,
            tokens_used=self.token_tracker.resolve(clean_output),
            cost_usd=self.token_tracker.cost_usd,
            promise_state=parsed[0] if parsed else "",
            promise_payload=parsed[1] if parsed else "",
        )

    # ------------------------------------------------------------ transport

    def _read_stdout(self, proc: subprocess.Popen) -> None:
        try:
            for raw in proc.stdout:  # type: ignore[union-attr]
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    msg = json.loads(raw)
                except (ValueError, TypeError):
                    continue  # tolerate non-protocol noise on stdout
                if isinstance(msg, dict):
                    self._queue.put(msg)
        finally:
            self._queue.put(None)

    @staticmethod
    def _drain_stderr(proc: subprocess.Popen, tail: deque[str]) -> None:
        try:
            for raw in proc.stderr:  # type: ignore[union-attr]
                if raw.strip():
                    tail.append(raw.rstrip())
        except (ValueError, OSError):
            pass

    def _send(self, msg: dict[str, Any]) -> None:
        proc = self._proc
        assert proc.stdin is not None
        with self._write_lock:
            proc.stdin.write(json.dumps(msg) + "\n")
            proc.stdin.flush()

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send one request and pump messages until its response arrives.

        Incoming agent requests (permissions) and notifications (updates) are
        dispatched inline, so a ``session/prompt`` can stay in flight for the
        whole iteration while tool calls stream past.
        """
        self._next_id += 1
        request_id = self._next_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})

        while True:
            try:
                msg = self._queue.get(timeout=self.idle_timeout)
            except queue.Empty:
                raise TimeoutError(method) from None
            if msg is None:
                raise _AgentExitedError(method)

            if "method" in msg:
                if "id" in msg:
                    self._handle_agent_request(msg)
                else:
                    self._handle_notification(msg)
                continue

            if msg.get("id") == request_id:
                if "error" in msg:
                    err = msg["error"] or {}
                    raise _AgentExitedError(
                        f"{method} failed: {err.get('message', 'unknown error')}"
                    )
                result = msg.get("result")
                return result if isinstance(result, dict) else {}
            # Response to a stale/unknown id — ignore.

    # ----------------------------------------------- agent-initiated traffic

    def _handle_agent_request(self, msg: dict[str, Any]) -> None:
        method = msg.get("method", "")
        params = msg.get("params") or {}
        if method == "session/request_permission":
            result: dict[str, Any] = self._answer_permission(params)
            self._send({"jsonrpc": "2.0", "id": msg["id"], "result": result})
            return
        # We advertised no fs/terminal capabilities; refuse anything else.
        self._send(
            {
                "jsonrpc": "2.0",
                "id": msg["id"],
                "error": {"code": -32601, "message": f"method not supported: {method}"},
            }
        )

    def _answer_permission(self, params: dict[str, Any]) -> dict[str, Any]:
        options = [o for o in params.get("options", []) if isinstance(o, dict)]
        if not options:
            return {"outcome": {"outcome": "cancelled"}}
        chosen = min(options, key=lambda o: _OPTION_KIND_RANK.get(o.get("kind", ""), 9))
        title = (params.get("toolCall") or {}).get("title", "")
        self._emit_line(f"[permission: {title or 'tool call'} → {chosen.get('name', chosen.get('optionId'))}]")
        return {"outcome": {"outcome": "selected", "optionId": chosen.get("optionId")}}

    def _handle_notification(self, msg: dict[str, Any]) -> None:
        if msg.get("method") != "session/update":
            return
        update = (msg.get("params") or {}).get("update") or {}
        kind = update.get("sessionUpdate", "")

        if kind == "agent_message_chunk":
            text = _content_text(update.get("content"))
            if text:
                self._result_text_parts.append(text)
                self._display_buf += text
                self._flush_display()
        elif kind == "tool_call":
            title = update.get("title", "")
            tool_kind = update.get("kind", "tool")
            self._emit_line(f"[{tool_kind}: {title}]" if title else f"[{tool_kind}]")
        elif kind == "plan":
            entries = update.get("entries") or []
            if entries:
                self._emit_line(f"[plan: {len(entries)} step(s)]")
        elif kind == "usage_update":
            self._latest_usage = update

    # -------------------------------------------------------------- helpers

    def _emit_line(self, line: str) -> None:
        if self._on_line is not None and line.strip():
            self._on_line(line)

    def _flush_display(self, final: bool = False) -> None:
        """Emit buffered agent text to on_line, one complete line at a time."""
        while "\n" in self._display_buf:
            line, self._display_buf = self._display_buf.split("\n", 1)
            self._emit_line(line)
        if final and self._display_buf.strip():
            self._emit_line(self._display_buf)
            self._display_buf = ""

    def _record_usage(self) -> None:
        """Feed the latest ``usage_update`` into the tracker, tolerating schema drift.

        ACP specifies cumulative ``used``/``size`` token counts plus an optional
        cost; some adapters also report input/output splits. Only the final
        snapshot is recorded, since the counts are cumulative per turn.
        """
        usage = self._latest_usage
        if not usage:
            return
        in_tok = int(usage.get("inputTokens") or usage.get("input_tokens") or 0)
        out_tok = int(usage.get("outputTokens") or usage.get("output_tokens") or 0)
        if not (in_tok or out_tok):
            in_tok = int(usage.get("used") or 0)
        cost_raw = usage.get("cost")
        if isinstance(cost_raw, dict):
            cost = float(cost_raw.get("amount") or 0.0)
        elif isinstance(cost_raw, int | float):
            cost = float(cost_raw)
        else:
            cost = 0.0
        if in_tok or out_tok or cost:
            self.token_tracker.record_usage(
                input_tokens=in_tok, output_tokens=out_tok, cost_usd=cost
            )

    def _shutdown(self, proc: subprocess.Popen) -> None:
        """Close the transport after a completed turn and reap the process."""
        try:
            if proc.stdin is not None:
                proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            terminate_process(proc)

    def _failure(self, message: str, *, returncode: int) -> AgentResult:
        self._emit_line(message)
        return AgentResult(
            stdout=message,
            returncode=returncode,
            success=False,
            has_completion_signal=False,
        )


def _content_text(content: Any) -> str:
    """Extract plain text from an ACP content block (or list of blocks)."""
    if isinstance(content, dict):
        return str(content.get("text", "")) if content.get("type") == "text" else ""
    if isinstance(content, list):
        return "".join(_content_text(block) for block in content)
    if isinstance(content, str):
        return content
    return ""


def _owloop_version() -> str:
    try:
        from importlib.metadata import version

        return version("owloop")
    except Exception:
        return "0"
