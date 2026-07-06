"""Tests for completion notifications (Phase 2 hook)."""

from __future__ import annotations

from pathlib import Path

from owloop import notifications
from owloop.engine import RunSummary


def _summary(stopped_reason: str, **kw) -> RunSummary:
    return RunSummary(
        iterations=kw.pop("iterations", 2),
        branch=kw.pop("branch", "main"),
        cwd=Path("."),
        main_repo_dir=Path("."),
        stopped_reason=stopped_reason,
        **kw,
    )


def test_build_message_includes_state_and_context() -> None:
    msg = notifications.build_message(_summary("blocked", blocker="missing API key", tokens_used=1234))
    assert "blocked" in msg
    assert "missing API key" in msg
    assert "1,234 tokens" in msg
    assert "main" in msg


def test_notify_noop_when_nothing_configured() -> None:
    assert notifications.notify_run_complete(_summary("stalled")) is False


def test_notify_skips_uninteresting_states() -> None:
    events: list[str] = []
    # max_iterations classifies to `exhausted` (notify), but a bare non-terminal
    # reason like all_specs_complete→success does notify; pick an interrupted run
    # which is NOT in the notify set.
    attempted = notifications.notify_run_complete(
        _summary("interrupted"),
        webhook_url="https://example.test/hook",
        emit=lambda k, **d: events.append(k),
    )
    assert attempted is False


def test_notify_force_overrides_state_gate(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(notifications, "_post_webhook", lambda *a, **k: calls.append("webhook"))
    attempted = notifications.notify_run_complete(
        _summary("interrupted"),
        webhook_url="https://example.test/hook",
        force=True,
    )
    assert attempted is True
    assert calls == ["webhook"]


def test_webhook_posts_json_payload(monkeypatch) -> None:
    captured: dict = {}

    class _FakeResp:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["data"] = request.data
        captured["method"] = request.method
        return _FakeResp()

    monkeypatch.setattr(notifications.urllib.request, "urlopen", _fake_urlopen)
    events: list[tuple[str, dict]] = []
    notifications.notify_run_complete(
        _summary("stalled"),
        webhook_url="https://example.test/hook",
        emit=lambda k, **d: events.append((k, d)),
    )

    assert captured["url"] == "https://example.test/hook"
    assert captured["method"] == "POST"
    import json

    body = json.loads(captured["data"])
    assert "owloop stalled" in body["text"]
    assert body["summary"]["stopped_reason"] == "stalled"
    assert any(k == "notification_sent" for k, _ in events)


def test_webhook_failure_never_raises(monkeypatch) -> None:
    def _boom(request, timeout=0):
        raise OSError("network down")

    monkeypatch.setattr(notifications.urllib.request, "urlopen", _boom)
    events: list[tuple[str, dict]] = []
    # max_tokens classifies to the `exhausted` terminal state (a notify state).
    # Must not raise.
    notifications.notify_run_complete(
        _summary("max_tokens"),
        webhook_url="https://example.test/hook",
        emit=lambda k, **d: events.append((k, d)),
    )
    assert any(k == "notification_failed" for k, _ in events)


def test_desktop_skips_gracefully_without_notifier(monkeypatch) -> None:
    monkeypatch.setattr(notifications, "_desktop_command", lambda msg: None)
    events: list[tuple[str, dict]] = []
    notifications.notify_run_complete(
        _summary("success"),
        desktop=True,
        emit=lambda k, **d: events.append((k, d)),
    )
    assert any(k == "notification_skipped" for k, _ in events)
