"""Tests for cross-platform sleep inhibition."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

from owloop.adapters import AgentResult, MockAdapter
from owloop.engine import EngineConfig, OwloopEngine
from owloop.sleep_inhibitor import SleepInhibitor


def _git_init(repo: Path) -> None:
    """Initialize a git repo with an initial commit so HEAD exists."""
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "README.md").write_text("# test", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)


def test_macos_start_stop(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")

    fake_proc = MagicMock()
    popen_calls: list[list[str]] = []

    def fake_popen(cmd, **_kwargs):
        popen_calls.append(cmd)
        return fake_proc

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    events: list[tuple[str, dict]] = []
    inhibitor = SleepInhibitor(emit=lambda kind, data: events.append((kind, data)))

    inhibitor.start()

    assert popen_calls == [["caffeinate", "-i", "-w", str(os.getpid())]]
    started = [(k, d) for k, d in events if k == "sleep_inhibitor_started"]
    assert started
    assert started[0][1]["platform"] == "macos"

    inhibitor.stop()

    assert fake_proc.terminate.called
    stopped = [(k, d) for k, d in events if k == "sleep_inhibitor_stopped"]
    assert stopped


def test_linux_start_stop_when_systemd_inhibit_available(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    fake_proc = MagicMock()
    popen_calls: list[list[str]] = []

    def fake_popen(cmd, **_kwargs):
        popen_calls.append(cmd)
        return fake_proc

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr("owloop.sleep_inhibitor.shutil.which", lambda _cmd: "/usr/bin/systemd-inhibit")

    events: list[tuple[str, dict]] = []
    inhibitor = SleepInhibitor(emit=lambda kind, data: events.append((kind, data)))

    inhibitor.start()

    assert popen_calls[0][0] == "systemd-inhibit"
    assert "--why=owloop autonomous run" in popen_calls[0]
    assert "--who=owloop" in popen_calls[0]
    assert "--mode=block" in popen_calls[0]
    assert "--what=idle:sleep:handle-lid-switch" in popen_calls[0]
    started = [(k, d) for k, d in events if k == "sleep_inhibitor_started"]
    assert started
    assert started[0][1]["platform"] == "linux"

    inhibitor.stop()
    assert fake_proc.terminate.called


def test_linux_emits_warning_when_systemd_inhibit_missing(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr("owloop.sleep_inhibitor.shutil.which", lambda _cmd: None)

    events: list[tuple[str, dict]] = []
    inhibitor = SleepInhibitor(emit=lambda kind, data: events.append((kind, data)))

    inhibitor.start()

    warnings = [(k, d) for k, d in events if k == "sleep_inhibitor_warning"]
    assert warnings
    assert "systemd-inhibit not found" in warnings[0][1]["reason"]
    assert not [k for k, _ in events if k == "sleep_inhibitor_started"]

    inhibitor.stop()


def test_windows_start_stop(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")

    calls: list[int] = []

    class FakeKernel32:
        def SetThreadExecutionState(self, flags: int) -> None:  # noqa: N802
            calls.append(flags)

    class FakeWinDLL:
        kernel32 = FakeKernel32()

    fake_ctypes = MagicMock()
    fake_ctypes.windll = FakeWinDLL()
    monkeypatch.setitem(sys.modules, "ctypes", fake_ctypes)

    events: list[tuple[str, dict]] = []
    inhibitor = SleepInhibitor(emit=lambda kind, data: events.append((kind, data)))

    inhibitor.start()

    ES_CONTINUOUS = 0x80000000  # noqa: N806
    ES_SYSTEM_REQUIRED = 0x00000001  # noqa: N806
    ES_AWAYMODE_REQUIRED = 0x00000040  # noqa: N806
    assert calls == [ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED]
    assert any(k == "sleep_inhibitor_started" and d["platform"] == "windows" for k, d in events)

    inhibitor.stop()

    assert calls == [
        ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED,
        ES_CONTINUOUS,
    ]
    assert any(k == "sleep_inhibitor_stopped" for k, _ in events)


def test_unsupported_platform_emits_warning(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "freebsd")

    events: list[tuple[str, dict]] = []
    inhibitor = SleepInhibitor(emit=lambda kind, data: events.append((kind, data)))

    inhibitor.start()

    warnings = [(k, d) for k, d in events if k == "sleep_inhibitor_warning"]
    assert warnings
    assert "unsupported platform" in warnings[0][1]["reason"]


def test_engine_starts_and_stops_inhibitor(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / "specs").mkdir()
    (repo / "specs" / "01-test.md").write_text("# spec", encoding="utf-8")

    start_calls: list[bool] = []
    stop_calls: list[bool] = []

    class FakeInhibitor:
        def __init__(self, emit):
            pass

        def start(self) -> None:
            start_calls.append(True)

        def stop(self) -> None:
            stop_calls.append(True)

    monkeypatch.setattr("owloop.engine.SleepInhibitor", FakeInhibitor)

    adapter = MockAdapter(
        responses=[
            AgentResult(
                stdout="plan done\n<promise>DONE</promise>",
                returncode=0,
                success=True,
                has_completion_signal=True,
                done_signal="<promise>DONE</promise>",
            )
        ]
    )
    config = EngineConfig(project_dir=repo, worktree=False, mode="plan", max_iterations=1)
    engine = OwloopEngine(config=config, adapter=adapter)

    summary = engine.run()

    assert summary.iterations == 1
    assert len(start_calls) == 1
    assert len(stop_calls) == 1


def test_engine_stops_inhibitor_on_keyboard_interrupt(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / "specs").mkdir()
    (repo / "specs" / "01-test.md").write_text("# spec", encoding="utf-8")

    stop_calls: list[bool] = []

    class FakeInhibitor:
        def __init__(self, emit):
            pass

        def start(self) -> None:
            pass

        def stop(self) -> None:
            stop_calls.append(True)

    class RaisingAdapter(MockAdapter):
        def run(self, prompt: str, cwd: Path, *, on_line=None):
            raise KeyboardInterrupt

    monkeypatch.setattr("owloop.engine.SleepInhibitor", FakeInhibitor)

    adapter = RaisingAdapter()
    config = EngineConfig(project_dir=repo, worktree=False, mode="build")
    engine = OwloopEngine(config=config, adapter=adapter)

    summary = engine.run()

    assert summary.stopped_reason == "interrupted"
    assert len(stop_calls) == 1
