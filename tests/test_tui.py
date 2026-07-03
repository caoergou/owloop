"""Tests for the OwloopTUI rendering helpers."""

import time

from rich.console import Console

from owloop.tui import AppState, OwloopTUI


def _render_to_text(app_method, state=None):
    """Render a TUI panel method to plain text via a recording Console."""
    tui = OwloopTUI()
    tui.console = Console(record=True)
    if state is not None:
        tui.state = state
    panel = app_method(tui)
    tui.console.print(panel)
    return tui.console.export_text()


def test_render_status_includes_current_spec_name():
    state = AppState(
        model="claude-sonnet",
        branch="feat/owl",
        iteration=2,
        specs=[
            {"name": "01-done.md", "done": True},
            {"name": "02-current.md", "done": False},
            {"name": "03-pending.md", "done": False},
        ],
    )
    text = _render_to_text(OwloopTUI._render_status, state)
    assert "02-current.md" in text


def test_render_specs_distinguishes_states():
    state = AppState(
        specs=[
            {"name": "01-done.md", "done": True},
            {"name": "02-current.md", "done": False},
            {"name": "03-pending.md", "done": False},
        ],
    )
    text = _render_to_text(OwloopTUI._render_specs, state)
    assert "01-done.md" in text
    assert "02-current.md" in text
    assert "03-pending.md" in text


def test_status_text_uses_ollie_branding():
    tui = OwloopTUI()
    tui.console = Console(record=True)
    tui.state = AppState(phase="starting", start_time=time.monotonic())
    text = str(tui._status_text())
    assert "Ollie" in text


def test_full_layout_includes_owl_and_specs():
    tui = OwloopTUI()
    layout = tui._build_layout()
    assert layout["owl"] is not None
    assert layout["specs"] is not None


def test_compact_layout_omits_owl_and_specs():
    tui = OwloopTUI()
    layout = tui._build_compact_layout()
    assert "owl" not in layout.children
    assert "specs" not in layout.children
    assert layout["status"] is not None
    assert layout["activity"] is not None


def test_forced_compact_mode():
    tui = OwloopTUI(compact=True)
    assert tui._compact is True
    assert tui._force_compact is True


def test_small_terminal_triggers_compact_layout():
    tui = OwloopTUI()
    tui.console = Console(width=60, height=20)
    assert tui._should_be_compact() is True


def test_update_layout_switches_to_compact():
    tui = OwloopTUI()
    tui.console = Console(width=60, height=20)
    tui._update_layout_for_size()
    assert tui._compact is True
