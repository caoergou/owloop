"""Display helpers for the owloop CLI."""

import sys
import threading
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from owloop import _brand
from owloop.sessions import classify_spec


def _banner_text(ascii: bool = False, no_color: bool = False) -> Text | str:
    """Return the owloop banner."""
    joined = (
        _brand.BRAND_BAR_ASCII
        if ascii
        else f"{_brand.OWL_EMOJI}  {_brand.BRAND_BAR}"
    )
    if no_color:
        return joined
    return Text.from_markup(f"[bold {_brand.AMBER}]{joined}[/]")


def render_progress_bar(done: int, total: int, width: int = 20, ascii: bool = False) -> str:
    filled = round(width * done / total) if total else 0
    filled = max(0, min(width, filled))
    pct = round(done / total * 100) if total else 0
    moon = _brand.ascii_moon_for_progress(done, total) if ascii else _brand.moon_for_progress(done, total)
    return (
        f"{moon} [{_brand.AMBER}]{'█' * filled}[/][{_brand.GRAY}]{'░' * (width - filled)}[/] {pct}%"
    )


def _format_spec_table(spec_paths: list[Path], verbose: bool = False) -> Table | list[Panel]:
    """Return either a compact Table or full Panels for the generated specs."""
    if verbose:
        return [
            Panel(
                sp.read_text(encoding="utf-8"),
                title=f"[bold]{sp.name}[/]",
                border_style=_brand.AMBER,
                padding=(1, 2),
            )
            for sp in spec_paths
        ]

    table = Table(
        title="Generated specs",
        border_style=_brand.AMBER,
        show_lines=False,
        padding=(0, 2),
    )
    table.add_column("File", style="bold")
    table.add_column("Title")
    table.add_column("Priority", justify="center")
    table.add_column("Status", justify="center")

    for sp in spec_paths:
        content = sp.read_text(encoding="utf-8")
        state = classify_spec(content)
        status_text = {
            "done": "[green]done[/]",
            "in_progress": f"[{_brand.AMBER}]in progress[/]",
            "pending": "[dim]pending[/]",
        }[state]
        priority = "—"
        title: str | None = None
        for line in content.splitlines():
            if line.strip().startswith("## Priority:"):
                priority = line.split(":", 1)[-1].strip()
            if line.startswith("# Spec:"):
                title = line.split(":", 1)[-1].strip()
        table.add_row(sp.name, title or "—", priority, status_text)

    return table


class AgentStreamDisplay:
    """Live display for streaming agent output.

    Layout: gray output lines scroll above, status bar stays at the bottom.

      [reading backend/app/api/orders.py]         ← scrolling gray
      Found 23 repeated try/except blocks          ← scrolling gray
      [running: grep -c "except" *.py]             ← scrolling gray
      ⠋ 0:32 · ~1.2k tokens                       ← always at bottom
    """

    BURST_THRESHOLD = 8
    SPINNERS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, console: Console, *, verbose: bool = False) -> None:
        self.console = console
        self.verbose = verbose
        self.start_time = time.monotonic()
        self._last_output = time.monotonic()
        self._burst_count = 0
        self._burst_suppressed = 0
        self._line_count = 0
        self._char_count = 0
        self._real_tokens = ""
        self._has_status = False
        self._frame = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._ticker: threading.Thread | None = None
        self._out = console.file or sys.stdout

    def start(self) -> None:
        self._draw_status()
        self._ticker = threading.Thread(target=self._tick, daemon=True)
        self._ticker.start()

    def stop(self) -> None:
        self._stop.set()
        if self._ticker:
            self._ticker.join(timeout=2)
        with self._lock:
            self._clear_status()
            self._flush_burst()

    @staticmethod
    def _is_noise(text: str) -> bool:
        if len(text) < 3 or not any(c.isalnum() for c in text):
            return True
        return "<promise>" in text

    def on_line(self, line: str) -> None:
        stripped = line.strip()
        if not stripped or self._is_noise(stripped):
            return

        with self._lock:
            now = time.monotonic()
            gap = now - self._last_output
            self._last_output = now
            self._line_count += 1
            self._char_count += len(stripped)

            if stripped.startswith("[usage:"):
                self._real_tokens = stripped[8:-1]
                self._clear_status()
                self._draw_status()
                return

            if self.verbose:
                elapsed = now - self.start_time
                self._clear_status()
                self._print_line(f"  [{elapsed:.1f}s] {stripped}")
                self._draw_status()
                return

            if gap < 0.05:
                self._burst_count += 1
                if self._burst_count > self.BURST_THRESHOLD:
                    self._burst_suppressed += 1
                    return
            else:
                if self._burst_suppressed > 0:
                    self._clear_status()
                    self._flush_burst()
                self._burst_count = 0

            self._clear_status()
            self._print_line(f"  {stripped}")
            self._draw_status()

    def _flush_burst(self) -> None:
        if self._burst_suppressed > 0:
            self._print_line(f"  ... ({self._burst_suppressed} lines)")
            self._burst_suppressed = 0

    def _print_line(self, text: str) -> None:
        self._out.write(f"\033[90m{text}\033[0m\n")
        self._out.flush()

    def _clear_status(self) -> None:
        if self._has_status:
            self._out.write("\r\033[K")
            self._out.flush()
            self._has_status = False

    def _build_status(self) -> str:
        elapsed = int(time.monotonic() - self.start_time)
        mins, secs = divmod(elapsed, 60)
        self._frame = (self._frame + 1) % len(self.SPINNERS)
        spinner = self.SPINNERS[self._frame]
        parts = [f"  {spinner} {mins}:{secs:02d}"]
        if self._real_tokens:
            parts.append(self._real_tokens)
        else:
            est = self._char_count // 4
            if est >= 1000:
                parts.append(f"~{est / 1000:.1f}k tokens")
            elif est > 0:
                parts.append(f"~{est} tokens")
        parts.append(f"{self._line_count} lines")
        return " · ".join(parts)

    def _draw_status(self) -> None:
        status = self._build_status()
        self._out.write(f"\r\033[K{status}")
        self._out.flush()
        self._has_status = True

    def _tick(self) -> None:
        while not self._stop.wait(0.5):
            with self._lock:
                if self._has_status:
                    self._out.write(f"\r\033[K{self._build_status()}")
                    self._out.flush()


def _ensure_init(cwd: Path, console: Console, *, ascii: bool = False) -> None:
    """Auto-initialize .owloop/ if it doesn't exist (silent, no example spec)."""
    owloop_path = cwd / ".owloop"
    if owloop_path.exists():
        return

    if not (cwd / ".git").exists():
        console.print("[red]Error:[/] Not a git repository. Run [bold]git init[/] first.")
        raise SystemExit(1)

    owloop_path.mkdir(parents=True)
    (owloop_path / "specs").mkdir()
    (owloop_path / "logs").mkdir()

    gitignore = cwd / ".gitignore"
    gitignore_entries = [".owloop/"]
    if gitignore.exists():
        existing = gitignore.read_text(encoding="utf-8")
        to_add = [e for e in gitignore_entries if e not in existing]
        if to_add:
            with open(gitignore, "a", encoding="utf-8") as f:
                f.write("\n# owloop\n")
                for entry in to_add:
                    f.write(f"{entry}\n")
    else:
        gitignore.write_text("# owloop\n" + "\n".join(gitignore_entries) + "\n", encoding="utf-8")

    console.print(f"[{_brand.GREEN}]✓[/] Initialized .owloop/")
