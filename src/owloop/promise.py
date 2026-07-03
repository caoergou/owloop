"""Parsing for the ``<promise>`` completion-signal protocol.

Supported signals:
- ``<promise>DONE</promise>`` — iteration succeeded.
- ``<promise>BLOCKED:reason</promise>`` — external blocker, loop should stop.
- ``<promise>DECIDE:question</promise>`` — human decision needed, loop should stop.
"""

from __future__ import annotations

import re

PROMISE_SIGNAL_RE = re.compile(r"<promise>(DONE|BLOCKED|DECIDE)(?::([^<]+))?</promise>")


def parse_promise_signal(text: str) -> tuple[str, str] | None:
    """Search ``text`` for a promise signal.

    Args:
        text: The agent's stdout.

    Returns:
        A ``(state, payload)`` tuple, or ``None`` if no recognized signal is found.
        ``payload`` is empty for ``DONE`` and stripped for ``BLOCKED``/``DECIDE``.
    """
    match = PROMISE_SIGNAL_RE.search(text)
    if not match:
        return None
    state = match.group(1)
    payload = (match.group(2) or "").strip()
    return state, payload
