"""Rich full-screen TUI for `owloop run` — driven by OwloopEngine events.

The TUI is brand-first: a large animated owl (Ollie) shows the loop's mood,
a status panel surfaces iteration/token/spec state, and a "What Ollie is doing"
panel translates raw agent activity into human-readable intent. Raw command
output is intentionally de-emphasized in full-screen mode and only surfaced in
the compact fallback or in the session log file.
"""

from __future__ import annotations

import itertools
import math
import random
import re
import signal
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from types import FrameType
from typing import Any

from rich.align import Align
from rich.console import Console, Group, RenderableType
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from owloop._brand import (
    AMBER,
    BRAND_BAR,
    BRAND_BAR_ASCII,
    CYAN,
    DIM_BLUE,
    GRAY,
    GREEN,
    MOON_PHASES_FULL,
    MOON_WHITE,
    NIGHT,
    OWL_SLEEP,
    RED,
    SPINNER_FRAMES,
    STAR_STYLE,
    TAGLINE,
    exit_hints,
    moon_for_progress,
    status_message,
    wake_message,
)
from owloop.engine import RunSummary, TerminalState

SCENE_W, SCENE_H = 36, 13
MIN_WIDTH, MIN_HEIGHT = 80, 24
_star_rng = random.Random(7)
STAR_CHARS = "·∗✦⋆˙"
STAR_FIELD = [
    (
        _star_rng.randint(0, SCENE_W - 1),
        _star_rng.randint(0, SCENE_H - 1),
        _star_rng.choice(STAR_CHARS),
        _star_rng.uniform(0, math.tau),
    )
    for _ in range(28)
]

# Human-readable translations of agent activity.
ACTIVITY_HINTS = [
    (re.compile(r"ruff\b", re.IGNORECASE), "Running lint checks"),
    (re.compile(r"pytest\b", re.IGNORECASE), "Running tests"),
    (re.compile(r"pyright\b", re.IGNORECASE), "Running type checks"),
    (re.compile(r"mypy\b", re.IGNORECASE), "Running type checks"),
    (re.compile(r"git\s+commit", re.IGNORECASE), "Committing changes"),
    (re.compile(r"git\s+push", re.IGNORECASE), "Pushing commits"),
    (re.compile(r"<promise>DONE</promise>", re.IGNORECASE), "Finishing iteration"),
    (re.compile(r"<promise>BLOCKED", re.IGNORECASE), "Stopped: external blocker"),
    (re.compile(r"<promise>DECIDE", re.IGNORECASE), "Waiting for human decision"),
]


def _format_elapsed(seconds: float) -> str:
    minutes = int(seconds // 60)
    return f"{minutes // 60}h {minutes % 60:02d}m"


@dataclass
class AppState:
    model: str = ""
    branch: str = ""
    cwd: str = ""
    main_repo_dir: str = ""
    max_iterations: int = 0
    max_tokens: int = 0
    iteration: int = 0
    specs: list[dict] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)
    start_time: float = 0.0
    blink: bool = False
    next_blink: float = 0.0
    phase: str = "starting"  # starting|working|stuck|done_signal|complete|error
    current_action: str = ""
    flash: tuple[str, str, float] | None = None
    done: bool = False
    stopped_reason: str = ""
    tokens_used: int = 0
    estimated_cost_usd: float = 0.0
    moon_frame: int = 0
    _spinner: str = "⠋"


class OwloopTUI:
    """Full-screen Live TUI. Use as a context manager around engine.run()."""

    def __init__(self, ascii: bool = False, no_color: bool = False, compact: bool = False) -> None:
        self.console = Console(no_color=no_color)
        self.ascii = ascii
        self._force_compact = compact
        self.state = AppState(start_time=time.monotonic(), next_blink=time.monotonic() + 5)
        self._compact = self._should_be_compact()
        self.layout = self._build_layout() if not self._compact else self._build_compact_layout()
        self.live = Live(
            self.layout, console=self.console, screen=True, auto_refresh=False
        )
        self._lock = threading.Lock()
        self._stop_ticker = threading.Event()
        self._ticker: threading.Thread | None = None
        self._live_started = False
        self._paused = False
        self._original_sigwinch: Callable[[int, FrameType | None], Any] | int | None = None

    def _should_be_compact(self) -> bool:
        """Return whether the TUI should use the compact single-column layout."""
        if self._force_compact:
            return True
        width, height = self.console.size
        return width < MIN_WIDTH or height < MIN_HEIGHT

    # ── lifecycle ──

    def _on_sigwinch(self, _signum: int, _frame: FrameType | None) -> None:
        """Terminal resized: re-evaluate layout on next render."""
        with self._lock:
            self._update_layout_for_size()
            self._render()

    def _play_wake_animation(self) -> None:
        """Show a brief wake-up message when the TUI starts."""
        brand = BRAND_BAR_ASCII if self.ascii else BRAND_BAR
        captions = [
            ("Ollie is waking up...", DIM_BLUE),
            ("Ready to work", AMBER),
        ]
        target = "activity" if self._compact else "right"
        for caption, border in captions:
            body = Group(
                Text(""),
                Text(brand, style=f"bold {AMBER}", justify="center"),
                Text(""),
                Text(caption, style=f"italic {MOON_WHITE}", justify="center"),
            )
            self.layout[target].update(
                Panel(body, border_style=border, style=f"on {NIGHT}", padding=(1, 2))
            )
            self.live.refresh()
            time.sleep(0.5)

    def __enter__(self) -> OwloopTUI:
        self.live.__enter__()
        self._live_started = True
        if hasattr(signal, "SIGWINCH"):
            self._original_sigwinch = signal.signal(signal.SIGWINCH, self._on_sigwinch)
        self._render()
        self._play_wake_animation()
        self._ticker = threading.Thread(target=self._tick_loop, daemon=True)
        self._ticker.start()
        return self

    def __exit__(self, *_exc: Any) -> None:
        self._stop_ticker.set()
        if self._ticker:
            self._ticker.join(timeout=1)
        if self._original_sigwinch is not None and hasattr(signal, "SIGWINCH"):
            signal.signal(signal.SIGWINCH, self._original_sigwinch)
            self._original_sigwinch = None
        if self._live_started:
            self.live.__exit__(*_exc)
            self._live_started = False

    def _tick_loop(self) -> None:
        frame_idx = 0
        while not self._stop_ticker.wait(0.25):
            with self._lock:
                now = time.monotonic()
                if now >= self.state.next_blink:
                    self.state.blink = not self.state.blink
                    self.state.next_blink = now + (0.25 if self.state.blink else random.uniform(3, 7))
                if self.state.phase == "working":
                    frame_idx = (frame_idx + 1) % len(SPINNER_FRAMES)
                    self.state._spinner = SPINNER_FRAMES[frame_idx]
                    self.state.moon_frame = (self.state.moon_frame + 1) % len(MOON_PHASES_FULL)
                self._render()

    # ── engine event handling ──

    # Events that require handing the terminal back to the caller for an
    # interactive confirm prompt (see EngineConfig.confirm_dirty/confirm_worktree
    # in engine.py). The prompt text itself is owned by the caller's callback,
    # not the TUI — this just steps out of the Live screen to make room for it.
    PROMPT_EVENTS = {"worktree_prompt", "dirty_workspace_warning"}

    def on_event(self, kind: str, data: dict) -> None:
        if self._paused:
            self.live.start()
            self._paused = False

        with self._lock:
            self._handle(kind, data)
            self._render()

        if kind in self.PROMPT_EVENTS:
            self.live.stop()
            self._paused = True

    def _log(self, line: str) -> None:
        self.state.logs.append(line)
        if len(self.state.logs) > 300:
            self.state.logs = self.state.logs[-300:]

    def _flash(self, text: str, style: str, seconds: float = 3.0) -> None:
        self.state.flash = (text, style, time.monotonic() + seconds)

    def _update_action(self, line: str) -> None:
        """Translate a raw agent output line into a human-readable activity."""
        for pattern, action in ACTIVITY_HINTS:
            if pattern.search(line):
                self.state.current_action = action
                return

    def _handle(self, kind: str, data: dict) -> None:
        s = self.state

        if kind == "session_info":
            s.model = data["model"]
            s.branch = data["branch"]
            s.cwd = data["cwd"]
            s.main_repo_dir = data["main_repo_dir"]
            s.max_iterations = data["max_iterations"]
            s.max_tokens = data.get("max_tokens", 0)
            s.specs = data["specs"]
            self._log(f"{wake_message()} · model {s.model} · branch {s.branch}")
        elif kind == "worktree_already_active":
            self._log(f"Running in isolated worktree: {data['path']}")
        elif kind == "worktree_skipped":
            self._log("worktree isolation disabled, running in current directory")
        elif kind == "worktree_prompt":
            self._log("Recommended to create isolated worktree (waiting for terminal input...)")
        elif kind == "worktree_auto_created":
            self._log("Non-interactive environment, automatically creating isolated worktree to protect main repository")
        elif kind in ("worktree_created", "worktree_branch_reused"):
            s.cwd = data["path"]
            self._log(f"✓ created and switched to worktree: {data['path']}")
        elif kind == "worktree_reused":
            s.cwd = data["path"]
            self._log(f"directory exists, entering: {data['path']}")
        elif kind == "worktree_declined":
            self._log("continue running in current directory (worktree isolation disabled)")
        elif kind == "worktree_failed":
            self._log("✗ failed to create worktree, continuing in current directory")
        elif kind == "all_specs_complete":
            s.phase = "complete"
            s.done = True
            s.current_action = "All specs already complete"
            self._log(f"all {data['spec_count']} specs complete, nothing to do")
        elif kind == "iteration_start":
            s.iteration = data["iteration"]
            s.phase = "working"
            s.current_action = "Reading the spec and codebase"
            self._log(f"── iteration {s.iteration} started ──")
        elif kind == "output_line":
            line = data["line"].rstrip()
            if line:
                self._log(line)
                self._update_action(line)
        elif kind == "tokens_update":
            s.tokens_used = data["total_tokens"]
            s.estimated_cost_usd = data.get("total_cost_usd", s.estimated_cost_usd)
        elif kind == "max_tokens_reached":
            s.phase = "complete"
            s.done = True
            s.current_action = "Token budget reached"
            self._log(f"⏱ token budget reached ({data['tokens']:,} / {data['limit']:,}), stopping loop")
            self._flash("⏱ token budget reached", f"bold {AMBER}")
        elif kind == "done_signal":
            s.phase = "done_signal"
            s.current_action = "Committing changes"
            self._log(f"✓ done signal detected: {data['signal']}")
            self._log(f"🌙 Loop closed on iteration {s.iteration}")
            self._flash(f"🌙 Loop closed on iteration {s.iteration}", f"bold {MOON_WHITE}")
        elif kind == "blocked":
            s.phase = "stuck"
            s.current_action = f"Blocked: {data['payload']}"
            self._log(f"✗ blocked: {data['payload']}")
            self._flash(f"✗ blocked: {data['payload']}", f"bold {RED}")
        elif kind == "decide":
            s.phase = "stuck"
            s.current_action = f"Decision needed: {data['payload']}"
            self._log(f"❓ decision needed: {data['payload']}")
            self._flash(f"❓ decision needed: {data['payload']}", f"bold {AMBER}")
        elif kind == "no_done_signal":
            self._log("⚠ no done signal detected, will retry in the next iteration")
        elif kind == "agent_failed":
            s.current_action = "Agent iteration failed"
            self._log(f"✗ agent failed (returncode={data['returncode']})")
        elif kind == "agent_timeout":
            s.current_action = "Agent timed out"
            self._log(f"⏱ iteration {data['iteration']} idle timeout, agent may be hung, terminated")
        elif kind == "preflight_failed":
            s.phase = "error"
            for issue in data["issues"]:
                self._log(f"✗ {issue}")
        elif kind == "dirty_workspace_warning":
            self._log("⚠ workspace has uncommitted changes that will not appear in the worktree")
        elif kind == "dirty_workspace_declined":
            s.phase = "error"
            self._log("cancelled — please commit or stash first")
        elif kind == "dirty_workspace_noninteractive_continue":
            self._log("non-interactive environment, ignoring uncommitted changes warning, continue")
        elif kind == "claude_config_copied":
            self._log(f"copied .claude/ config to worktree: {data['path']}")
        elif kind == "stuck_warning":
            s.phase = "stuck"
            self._log(f"💤 {data['consecutive_failures']} consecutive failures, agent may be stuck")
            self._flash("💤 may be stuck, retrying...", f"bold {GRAY}")
        elif kind == "fix_loop_warning":
            files = ", ".join(data["files"][:3])
            self._log(f"⚠ fix loop detected: {files} modified for {data['consecutive']} consecutive iterations")
            self._flash("⚠ possible fix loop", f"bold {RED}")
        elif kind == "max_duration_reached":
            s.done = True
            s.phase = "complete"
            s.current_action = "Maximum run time reached"
            self._log(f"⏱ reached maximum run time ({data['minutes']} min), stopping loop")
            self._flash("⏱ time up", f"bold {AMBER}")
        elif kind == "push_retry":
            self._log(f"push failed, creating remote branch {data['branch']}...")
        elif kind == "iteration_end":
            if "specs" in data:
                s.specs = data["specs"]
            s.phase = "working"
            s.current_action = "Preparing next iteration"
        elif kind == "interrupted":
            s.phase = "error"
            self._log("stopped (Ctrl+C)")

    # ── rendering ──

    @staticmethod
    def _is_done(spec: dict) -> bool:
        status = spec.get("status")
        return status == "done" or (status is None and bool(spec.get("done")))

    def _current_spec_name(self) -> str:
        for spec in self.state.specs:
            if not self._is_done(spec):
                return str(spec.get("name", ""))
        return ""

    def _status_text(self) -> Text:
        s = self.state
        if s.flash and time.monotonic() < s.flash[2]:
            text, style, _ = s.flash
            return Text(text, style=style)
        spec_name = self._current_spec_name()
        message = status_message(s.phase, s.iteration, spec_name)
        if s.phase == "complete":
            style = f"bold {AMBER}"
        elif s.phase == "error":
            style = f"bold {RED}"
        elif s.phase == "stuck":
            style = f"bold {GRAY}"
        elif s.phase == "done_signal":
            style = f"bold {MOON_WHITE}"
        else:
            style = f"bold {AMBER}"
        return Text(message, style=style)

    def _render_header(self) -> Panel:
        s = self.state
        done = sum(1 for spec in s.specs if self._is_done(spec))
        total = len(s.specs) or 1
        if s.phase == "working":
            moon = MOON_PHASES_FULL[s.moon_frame]
        else:
            moon = moon_for_progress(done, total)
        grid = Table.grid(expand=True)
        grid.add_column(ratio=1)
        grid.add_column(justify="right")
        grid.add_row(
            Text(TAGLINE, style=f"italic {GRAY}"),
            Text(f"{_format_elapsed(time.monotonic() - s.start_time)} elapsed", style=DIM_BLUE),
        )
        return Panel(grid, title=f"{moon} owloop", title_align="left", border_style=AMBER, style=f"on {NIGHT}")

    def _render_status(self) -> Panel:
        s = self.state
        done = sum(1 for spec in s.specs if self._is_done(spec))
        table = Table.grid(padding=(0, 1))
        table.add_column(style=f"dim {GRAY}")
        table.add_column()
        table.add_row("Model", Text(s.model or "—", style=CYAN))
        table.add_row(
            "Iteration",
            Text(f"#{s.iteration}" + (f" / {s.max_iterations}" if s.max_iterations else ""), style=f"bold {MOON_WHITE}"),
        )
        table.add_row("Branch", Text(s.branch or "—", style=GREEN))
        if s.tokens_used:
            token_text = f"{s.tokens_used:,}"
            if s.max_tokens:
                token_text += f" / {s.max_tokens:,}"
            table.add_row("Tokens", Text(token_text, style=CYAN))
        if s.estimated_cost_usd:
            table.add_row("Est. cost", Text(f"${s.estimated_cost_usd:,.4f}", style=CYAN))
        if s.specs:
            table.add_row("Specs", Text(f"{done}/{len(s.specs)} done", style=GREEN))
        current_spec = self._current_spec_name()
        if current_spec:
            table.add_row("Current Spec", Text(current_spec, style=f"bold {AMBER}"))
        table.add_row("Status", self._status_text())
        return Panel(table, title="Status", title_align="left", border_style=DIM_BLUE, style=f"on {NIGHT}")

    def _render_activity(self) -> Panel:
        """Show what Ollie is doing instead of raw command output."""
        s = self.state
        rows: list[RenderableType] = []

        if s.phase == "working" and s.iteration > 0:
            spinner = getattr(s, "_spinner", "⠋")
            action = s.current_action or "Working on the current spec"
            rows.append(Text(f"{spinner} {action}", style=f"bold {AMBER}"))
        elif s.current_action:
            rows.append(Text(s.current_action, style=f"bold {MOON_WHITE}"))
        else:
            rows.append(Text("Ready to start", style=f"dim {GRAY}"))

        recent = [self._clean_log_line(line) for line in s.logs[-20:]]
        recent = [line for line in recent if line]
        if recent:
            rows.append(Text(""))
            for line in recent[-10:]:
                rows.append(Text(f"  · {line}", style=f"dim {GRAY}", no_wrap=True, overflow="ellipsis"))

        return Panel(
            Group(*rows),
            title="What Ollie is doing",
            title_align="left",
            border_style=DIM_BLUE,
            style=f"on {NIGHT}",
        )

    def _render_specs(self) -> Panel:
        s = self.state
        body: RenderableType
        if not s.specs:
            body = Text("(no specs)", style=f"dim {GRAY}")
        else:
            rows = []
            for spec in s.specs:
                status = spec.get("status")
                name = spec.get("name", "")
                if self._is_done(spec):
                    rows.append(Text(f"✓ {name}", style=GREEN))
                elif status == "in_progress":
                    rows.append(Text(f"🦉 {name}", style=f"bold {AMBER}"))
                else:
                    rows.append(Text(f"○ {name}", style=f"dim {GRAY}"))
            body = Group(*rows)
        return Panel(body, title="Specs", title_align="left", border_style=DIM_BLUE, style=f"on {NIGHT}")

    def _render_owl_scene(self) -> Panel:
        s = self.state
        grid = [[" "] * SCENE_W for _ in range(SCENE_H)]
        styles = [[""] * SCENE_W for _ in range(SCENE_H)]
        t = time.monotonic() - s.start_time

        for x, y, ch, phase in STAR_FIELD:
            brightness = (math.sin(t * 0.5 + phase) + 1) / 2
            if brightness > 0.6:
                grid[y][x] = ch
                styles[y][x] = STAR_STYLE

        text = Text(justify="center")
        for y in range(SCENE_H):
            for style, group in itertools.groupby(range(SCENE_W), key=lambda x: styles[y][x]):
                chars = "".join(grid[y][x] for x in group)
                text.append(chars, style=style or None)
            if y < SCENE_H - 1:
                text.append("\n")

        return Panel(
            Align.center(text, vertical="middle"),
            title="Owloop",
            subtitle=BRAND_BAR_ASCII if self.ascii else BRAND_BAR,
            subtitle_align="center",
            border_style=DIM_BLUE,
            style=f"on {NIGHT}",
            height=SCENE_H + 2,
        )

    @staticmethod
    def _clean_log_line(line: str) -> str:
        """Strip ANSI escapes, trim whitespace, and collapse repeated spaces."""
        line = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", line)
        return " ".join(line.split())

    def _render_log(self) -> Panel:
        """Compact-mode log panel (raw output is only shown here)."""
        recent = [self._clean_log_line(line) for line in self.state.logs[-12:]]
        recent = [line for line in recent if line]
        rows = []
        for i, line in enumerate(recent):
            is_latest = i == len(recent) - 1
            prefix = "▸" if is_latest else " "
            style = f"bold {MOON_WHITE}" if is_latest else GRAY
            rows.append(Text(f"{prefix} {line}", style=style, no_wrap=True, overflow="ellipsis"))
        if self.state.phase == "working" and self.state.iteration > 0 and not recent:
            spinner = getattr(self.state, "_spinner", "⠋")
            rows.append(Text(
                f"  {spinner} claude -p running, output will appear when this iteration ends...",
                style=f"dim italic {GRAY}", no_wrap=True
            ))
        return Panel(
            Group(*rows) if rows else Text(""),
            title="Activity Log",
            title_align="left",
            border_style=DIM_BLUE,
            style=f"on {NIGHT}",
        )

    def _render_footer(self) -> Panel:
        s = self.state
        done = sum(1 for spec in s.specs if self._is_done(spec))
        total = len(s.specs) or 1
        width = 40
        filled = int(width * done / total)
        bar = Text()
        bar.append("█" * filled, style=AMBER)
        bar.append("░" * (width - filled), style=DIM_BLUE)
        grid = Table.grid(expand=True)
        grid.add_column(ratio=1)
        grid.add_column(justify="right")
        loop_indicator = " ↻" if s.phase == "working" else ""
        grid.add_row(bar, Text(f"ctrl+c to stop{loop_indicator}", style=f"dim {GRAY}"))
        return Panel(grid, border_style=DIM_BLUE, style=f"on {NIGHT}")

    def _build_layout(self) -> Layout:
        layout = Layout(name="root")
        layout.split(
            Layout(name="header", size=3),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=3),
        )
        layout["body"].split_row(Layout(name="left", ratio=2), Layout(name="right", ratio=3))
        layout["left"].split(Layout(name="status", size=10), Layout(name="specs", ratio=1))
        layout["right"].update(Layout(name="activity", ratio=1))
        return layout

    def _build_compact_layout(self) -> Layout:
        """Single-column fallback for small terminals."""
        layout = Layout(name="root")
        layout.split(
            Layout(name="header", size=3),
            Layout(name="status", size=8),
            Layout(name="activity", size=12),
            Layout(name="log", ratio=1),
            Layout(name="footer", size=3),
        )
        return layout

    def _update_layout_for_size(self) -> None:
        """Switch between full and compact layout based on terminal dimensions."""
        if self._force_compact:
            wants_compact = True
        else:
            width, height = self.console.size
            wants_compact = width < MIN_WIDTH or height < MIN_HEIGHT
        if wants_compact == self._compact:
            return
        self._compact = wants_compact
        self.layout = (
            self._build_compact_layout() if self._compact else self._build_layout()
        )
        self.live.update(self.layout, refresh=False)

    def _render(self) -> None:
        if self._paused:
            return
        self._update_layout_for_size()
        self.layout["header"].update(self._render_header())
        self.layout["footer"].update(self._render_footer())
        if self._compact:
            self.layout["status"].update(self._render_status())
            self.layout["activity"].update(self._render_activity())
            self.layout["log"].update(self._render_log())
        else:
            self.layout["status"].update(self._render_status())
            self.layout["specs"].update(self._render_specs())
            self.layout["right"].update(self._render_activity())
        self.live.refresh()

    # ── exit summary ──

    FAILED_REASONS = {"preflight_failed", "dirty_workspace_declined"}

    def print_exit_summary(self, summary: RunSummary) -> None:
        s = self.state
        failed = summary.stopped_reason in self.FAILED_REASONS

        if failed:
            owl = Text("\n".join(OWL_SLEEP), style=f"dim {RED}", justify="center")
            lines: list[RenderableType] = [Align.center(Text("✗ owloop failed to start", style=f"bold {RED}")), Text("")]
            for issue in summary.issues or []:
                lines.append(Align.center(Text(f"· {issue}", style=f"dim {GRAY}")))
            body = Group(owl, Text(""), *lines)
            self.console.print(Panel(body, border_style=RED, style=f"on {NIGHT}", padding=(1, 4), width=56))
            return

        elapsed = time.monotonic() - s.start_time
        owl = Text("\n".join(OWL_SLEEP), style=f"dim {AMBER}", justify="center")

        facts = Table.grid(padding=(0, 2))
        facts.add_column(style=f"dim {GRAY}", justify="right")
        facts.add_column(style=MOON_WHITE)
        facts.add_row("Branch", summary.branch)
        if s.specs:
            done = sum(1 for spec in s.specs if self._is_done(spec))
            facts.add_row("Specs", Text(f"{done}/{len(s.specs)} done", style=f"bold {GREEN}"))
        facts.add_row("Iteration", str(summary.iterations))
        facts.add_row("Stopped reason", summary.stopped_reason)
        if summary.blocker:
            facts.add_row("Blocker", summary.blocker)
        if summary.decision_question:
            facts.add_row("Decision", summary.decision_question)
        if summary.tokens_used:
            facts.add_row("Tokens", f"{summary.tokens_used:,}")
        if summary.estimated_cost_usd:
            facts.add_row("Est. cost", f"${summary.estimated_cost_usd:,.4f}")
        facts.add_row("Time", _format_elapsed(elapsed))

        hints_lines = [
            Text(line, style=f"dim {GRAY}")
            for line in exit_hints(summary.branch, summary.iterations, summary.cwd, summary.main_repo_dir)
        ]

        # `exhausted`/`stalled` are not successes — the headline and border must
        # not read as a clean "complete".
        if summary.state == TerminalState.EXHAUSTED:
            headline = Text("⚠ owloop stopped — budget exhausted, work not finished", style=f"bold {RED}")
            border = RED
        elif summary.state == TerminalState.STALLED:
            headline = Text("⚠ owloop stalled — no progress", style=f"bold {RED}")
            border = RED
        else:
            headline = Text("🌅 owloop complete", style=f"bold {AMBER}")
            border = AMBER

        body = Group(
            owl,
            Text(""),
            Align.center(headline),
            Text(""),
            Align.center(facts),
            Text(""),
            Align.center(Group(*hints_lines)),
        )
        self.console.print(Panel(body, border_style=border, style=f"on {NIGHT}", padding=(1, 4), width=56))
