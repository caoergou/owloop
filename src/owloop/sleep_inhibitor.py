"""Cross-platform sleep inhibition for long-running owloop runs.

`SleepInhibitor` is a small helper that prevents the OS from going to sleep
while an `owloop run` is active. It uses `caffeinate` on macOS,
`systemd-inhibit` on Linux, and `SetThreadExecutionState` on Windows.
Failures are emitted as warnings; they never abort the run.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from typing import Any

EmitCallback = Callable[[str, dict], None]


class SleepInhibitor:
    """Platform-aware sleep inhibitor with explicit start/stop lifecycle."""

    def __init__(self, emit: EmitCallback | None = None) -> None:
        self.emit = emit or (lambda _kind, _data: None)
        self._process: subprocess.Popen | None = None

    def _emit(self, kind: str, **data: Any) -> None:
        """Forward an event to the configured callback as (kind, data_dict)."""
        self.emit(kind, data)

    def start(self) -> None:
        """Activate sleep inhibition for the current platform."""
        if sys.platform == "darwin":
            self._start_macos()
        elif sys.platform == "linux":
            self._start_linux()
        elif sys.platform == "win32":
            self._start_windows()
        else:
            self._emit(
                "sleep_inhibitor_warning",
                reason=f"unsupported platform: {sys.platform}",
            )

    def _start_macos(self) -> None:
        cmd = ["caffeinate", "-i", "-w", str(os.getpid())]
        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._emit("sleep_inhibitor_started", platform="macos", command=" ".join(cmd))
        except (OSError, subprocess.SubprocessError) as exc:
            self._emit("sleep_inhibitor_warning", reason=f"failed to start caffeinate: {exc}")

    def _start_linux(self) -> None:
        if not shutil.which("systemd-inhibit"):
            self._emit("sleep_inhibitor_warning", reason="systemd-inhibit not found")
            return

        cmd = [
            "systemd-inhibit",
            "--why=owloop autonomous run",
            "--who=owloop",
            "--mode=block",
            "--what=idle:sleep:handle-lid-switch",
            "sleep",
            "86400",
        ]
        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._emit("sleep_inhibitor_started", platform="linux", command=" ".join(cmd))
        except (OSError, subprocess.SubprocessError) as exc:
            self._emit(
                "sleep_inhibitor_warning",
                reason=f"failed to start systemd-inhibit: {exc}",
            )

    def _start_windows(self) -> None:
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            ES_CONTINUOUS = 0x80000000  # noqa: N806
            ES_SYSTEM_REQUIRED = 0x00000001  # noqa: N806
            ES_AWAYMODE_REQUIRED = 0x00000040  # noqa: N806
            kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
            )
            self._emit("sleep_inhibitor_started", platform="windows")
        except Exception as exc:  # noqa: BLE001
            self._emit(
                "sleep_inhibitor_warning",
                reason=f"SetThreadExecutionState failed: {exc}",
            )

    def stop(self) -> None:
        """Release sleep inhibition. Safe to call multiple times."""
        if sys.platform == "win32":
            self._stop_windows()
            return

        if self._process is not None:
            try:
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait(timeout=5)
            except (OSError, subprocess.SubprocessError) as exc:
                self._emit(
                    "sleep_inhibitor_warning",
                    reason=f"failed to stop inhibitor: {exc}",
                )
            finally:
                self._process = None
        self._emit("sleep_inhibitor_stopped", platform=sys.platform)

    def _stop_windows(self) -> None:
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            ES_CONTINUOUS = 0x80000000  # noqa: N806
            kernel32.SetThreadExecutionState(ES_CONTINUOUS)
            self._emit("sleep_inhibitor_stopped", platform="windows")
        except Exception as exc:  # noqa: BLE001
            self._emit(
                "sleep_inhibitor_warning",
                reason=f"failed to reset execution state: {exc}",
            )
