"""Completion notifications — tell the operator when an unattended loop stops.

An overnight loop that halts silently at 2 a.m. (blocked on a missing key,
stalled on a persistent error, or simply out of budget) wastes the whole night.
This module fires a best-effort notification when a run ends: a webhook POST
(Slack-compatible ``{"text": ...}`` plus a structured ``summary``) and/or a
native desktop notification. Everything here is best-effort — a failed
notification never raises into the engine and never changes the run outcome.

Zero extra dependencies: the webhook uses ``urllib`` and desktop notifications
shell out to whatever native tool exists (``osascript`` / ``notify-send`` /
``powershell``), degrading to a no-op when none is available.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from owloop.engine import RunSummary

EmitFn = Callable[..., None]

# Terminal states an operator should be told about the moment they happen. A
# clean success is included so "it finished" also reaches the phone; the
# attention-worthy states (blocked/decide/stalled/exhausted/tampered) are the
# reason the hook exists.
_NOTIFY_STATES = {
    "success",
    "blocked",
    "decide",
    "stalled",
    "exhausted",
    "tampered",
}

_STATE_EMOJI = {
    "success": "✅",
    "blocked": "⛔",
    "decide": "❓",
    "stalled": "🌀",
    "exhausted": "⌛",
    "tampered": "⚠️",
    "failed": "❌",
    "interrupted": "✋",
}


def build_message(summary: RunSummary) -> str:
    """Compose a one-line human-readable notification headline."""
    state = summary.state
    emoji = _STATE_EMOJI.get(state, "🦉")
    parts = [f"{emoji} owloop {state}"]
    if summary.blocker:
        parts.append(f"blocker: {summary.blocker}")
    if summary.decision_question:
        parts.append(f"decision: {summary.decision_question}")
    parts.append(f"{summary.iterations} iteration(s) on {summary.branch}")
    if summary.tokens_used:
        parts.append(f"{summary.tokens_used:,} tokens")
    return " · ".join(parts)


def _post_webhook(url: str, message: str, summary: RunSummary, emit: EmitFn) -> None:
    payload = json.dumps(
        {"text": message, "summary": summary.as_dict()},
        default=str,
    ).encode("utf-8")
    request = urllib.request.Request(  # noqa: S310 - operator-supplied https(s) webhook, same trust as their own shell
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            emit("notification_sent", channel="webhook", status=getattr(response, "status", 0))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        emit("notification_failed", channel="webhook", error=str(exc))


def _desktop_command(message: str) -> list[str] | None:
    """Return an argv for a native desktop notification, or None if unsupported."""
    title = "owloop"
    if sys.platform == "darwin" and shutil.which("osascript"):
        safe = message.replace('"', "'")
        return ["osascript", "-e", f'display notification "{safe}" with title "{title}"']
    if sys.platform.startswith("linux") and shutil.which("notify-send"):
        return ["notify-send", title, message]
    if sys.platform == "win32" and shutil.which("powershell"):
        safe = message.replace("'", "`'")
        script = (
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
            "ContentType=WindowsRuntime] > $null; "
            f"Write-Output '{safe}'"
        )
        return ["powershell", "-NoProfile", "-Command", script]
    return None


def _send_desktop(message: str, emit: EmitFn) -> None:
    cmd = _desktop_command(message)
    if cmd is None:
        emit("notification_skipped", channel="desktop", reason="no native notifier found")
        return
    try:
        subprocess.run(cmd, capture_output=True, timeout=10, check=False)
        emit("notification_sent", channel="desktop")
    except (OSError, subprocess.SubprocessError) as exc:
        emit("notification_failed", channel="desktop", error=str(exc))


def notify_run_complete(
    summary: RunSummary,
    *,
    webhook_url: str | None = None,
    desktop: bool = False,
    emit: EmitFn | None = None,
    force: bool = False,
) -> bool:
    """Fire configured notifications for a finished run. Never raises.

    Returns True if at least one channel was attempted. Notifications are only
    sent for attention-worthy terminal states (``_NOTIFY_STATES``) unless
    ``force`` is set. ``emit`` receives ``notification_*`` events for the UI /
    event log.
    """
    emit = emit or (lambda *_a, **_k: None)
    if not webhook_url and not desktop:
        return False
    if not force and summary.state not in _NOTIFY_STATES:
        return False

    message = build_message(summary)
    attempted = False
    if webhook_url:
        _post_webhook(webhook_url, message, summary, emit)
        attempted = True
    if desktop:
        _send_desktop(message, emit)
        attempted = True
    return attempted
