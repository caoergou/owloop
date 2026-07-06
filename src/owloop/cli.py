"""owloop CLI — entry point for uvx owloop / owloop commands."""

import os
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.text import Text

from owloop import _brand
from owloop.adapters import get_adapter
from owloop.engine import EngineConfig, OwloopEngine
from owloop.paths import resolve_specs_dir
from owloop.report import ReportGenerator
from owloop.report_ai import AIReportInsightsGenerator
from owloop.reporter import ConsoleReporter
from owloop.spec_from_issue import IssueToSpecConverter
from owloop.spec_generator import SpecGenerationError, SpecGenerator
from owloop.spec_linter import LintReport, SpecLinter
from owloop.tui import OwloopTUI

DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")

SPEC_TEMPLATE = """\
# Spec: {name}

## Priority: {priority}

## Requirements
- [ ] TODO: describe what needs to be done

## Acceptance Criteria
- [ ] TODO: shell command → expected output
      Verify: `echo "replace with real verification command"`

## Exclusions
- Do NOT modify files outside the scope described above
- Do NOT change any external API behavior
- Do NOT modify pyproject.toml, uv.lock, or other config files

## Style
- Follow existing project conventions

## Verification
After each change: run your lint/test commands, commit only if clean.

Output when complete: `<promise>DONE</promise>`
"""


CHECKED_BOX_RE = re.compile(r"- \[[xX]\]")

MAX_TOKENS_UNITS = {
    "k": 1_000,
    "w": 10_000,
    "m": 1_000_000,
}


def parse_max_tokens(value: str) -> int:
    """Parse a token limit, supporting shorthand like 10k, 1w, 2m.

    Args:
        value: Raw user input. Plain integers pass through; suffixes
            ``k`` (thousand), ``w`` (ten-thousand), and ``m`` (million)
            are expanded.

    Returns:
        Token count as an integer.

    Raises:
        click.BadParameter: if the value cannot be parsed.
    """
    value = value.strip().lower()
    if not value:
        raise click.BadParameter("token limit cannot be empty")

    if value.isdigit():
        return int(value)

    suffix = value[-1]
    if suffix not in MAX_TOKENS_UNITS:
        raise click.BadParameter(
            f"invalid token limit: {value!r}. Use a number or add k/w/m (e.g. 10k, 1w, 2m)"
        )

    number_part = value[:-1]
    if not number_part or not number_part.replace(".", "", 1).isdigit():
        raise click.BadParameter(
            f"invalid token limit: {value!r}. Use a number or add k/w/m (e.g. 10k, 1w, 2m)"
        )

    number = float(number_part)
    return int(number * MAX_TOKENS_UNITS[suffix])


class MaxTokensParamType(click.ParamType):
    """Click parameter type that parses token limit shorthand."""

    name = "tokens"

    def convert(self, value: object, param: click.Parameter | None, ctx: click.Context | None) -> int:
        if isinstance(value, int):
            return value
        return parse_max_tokens(str(value))


def classify_spec(content: str) -> str:
    lowered = content.lower()
    if "status: complete" in lowered:
        return "done"
    if "status: in progress" in lowered:
        return "in_progress"
    if CHECKED_BOX_RE.search(content):
        return "in_progress"
    return "pending"


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


def _print_check_report(console: Console, report: LintReport, *, ascii: bool = False) -> None:
    """Render a Rich report from a SpecLinter lint result."""
    check_icon = "+" if ascii else "✓"
    error_icon = "x" if ascii else "✗"
    warn_icon = "!" if ascii else "⚠"

    console.print()
    console.print("[bold]owloop check[/]")
    console.print(f"[dim]{'─' * 12}[/]")
    console.print(f"{check_icon} {report.spec_count} specs scanned")

    if report.error_count or report.warning_count:
        console.print(
            f"[{_brand.RED}]{error_icon} {report.error_count} error"
            f"{'s' if report.error_count != 1 else ''}[/], "
            f"[{_brand.AMBER}]{warn_icon} {report.warning_count} warning"
            f"{'s' if report.warning_count != 1 else ''}[/]"
        )
    else:
        console.print(f"[{_brand.GREEN}]{check_icon} 0 errors, 0 warnings[/]")

    for file_name, findings in report.results.items():
        if not findings:
            continue
        console.print()
        console.print(file_name)
        for finding in findings:
            if finding.severity == "error":
                icon = f"[{_brand.RED}]{error_icon}[/]"
            else:
                icon = f"[{_brand.AMBER}]{warn_icon}[/]"
            console.print(f"  {icon} {finding.message}")
    console.print()


def _cli_options() -> tuple[bool, bool, bool, bool]:
    """Read global --ascii / --no-color / --compact / --verbose flags from the current Click context."""
    ctx = click.get_current_context()
    obj = ctx.ensure_object(dict)
    return bool(obj.get("ascii")), bool(obj.get("no_color")), bool(obj.get("compact")), bool(obj.get("verbose"))


class AgentStreamDisplay:
    """Live display for streaming agent output.

    Features:
    - Dim gray output for each meaningful line
    - Burst folding: rapid-fire lines (file contents) collapsed to "... (N lines)"
    - Status bar: updates in-place with spinner, elapsed time, ~tokens, last output
    - Shows status bar when agent is idle (thinking) for >2 seconds
    """

    BURST_THRESHOLD = 8
    THINKING_DELAY = 2.0
    SPINNERS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, console: Console, *, verbose: bool = False) -> None:
        self.console = console
        self.verbose = verbose
        self.start_time = time.monotonic()
        self._last_output = time.monotonic()
        self._burst_count = 0
        self._burst_suppressed = 0
        self._char_count = 0
        self._recent: list[str] = []
        self._has_status = False
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._ticker: threading.Thread | None = None
        self._out = console.file or sys.stdout

    def start(self) -> None:
        self._ticker = threading.Thread(target=self._tick, daemon=True)
        self._ticker.start()

    def stop(self) -> None:
        self._stop.set()
        if self._ticker:
            self._ticker.join(timeout=2)
        with self._lock:
            self._clear_status()
            self._flush_burst()

    def on_line(self, line: str) -> None:
        stripped = line.strip()
        if not stripped:
            return

        with self._lock:
            now = time.monotonic()
            gap = now - self._last_output
            self._last_output = now
            self._char_count += len(stripped)

            self._recent.append(stripped[:80])
            if len(self._recent) > 3:
                self._recent.pop(0)

            self._clear_status()

            if self.verbose:
                elapsed = now - self.start_time
                self.console.print(f"  [dim][{elapsed:.1f}s][/] {stripped}")
                return

            if gap < 0.05:
                self._burst_count += 1
                if self._burst_count > self.BURST_THRESHOLD:
                    self._burst_suppressed += 1
                    return
            else:
                self._flush_burst()
                self._burst_count = 0

            self.console.print(f"  [dim]{stripped}[/]")

    def _flush_burst(self) -> None:
        if self._burst_suppressed > 0:
            self.console.print(f"  [dim]  ... ({self._burst_suppressed} lines)[/]")
            self._burst_suppressed = 0

    def _clear_status(self) -> None:
        if self._has_status:
            self._out.write("\r\033[K")
            self._out.flush()
            self._has_status = False

    def _format_tokens(self, chars: int) -> str:
        tokens = chars // 4
        if tokens >= 1000:
            return f"~{tokens / 1000:.1f}k"
        return f"~{tokens}"

    def _tick(self) -> None:
        frame = 0
        first_output_logged = False
        while not self._stop.wait(0.5):
            with self._lock:
                now = time.monotonic()
                idle = now - self._last_output
                elapsed = int(now - self.start_time)
                mins, secs = divmod(elapsed, 60)

                if idle < self.THINKING_DELAY:
                    continue

                if self.verbose and not first_output_logged and self._char_count == 0:
                    first_output_logged = True
                    self.console.print(f"  [dim][{mins}:{secs:02d}] waiting for claude -p to produce output...[/]")
                    continue

                frame = (frame + 1) % len(self.SPINNERS)
                tok = self._format_tokens(self._char_count)

                last = ""
                if self._recent:
                    last = self._recent[-1]
                    if len(last) > 50:
                        last = last[:47] + "..."

                hint = "waiting for output..." if self._char_count == 0 else ""
                status = f"  {self.SPINNERS[frame]} {mins}:{secs:02d} · {tok} tokens"
                if hint:
                    status += f"  {hint}"
                elif last:
                    status += f"  │ {last}"

                self._out.write(f"\r\033[K{status}")
                self._out.flush()
                self._has_status = True


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
    gitignore_entries = [".owloop/logs/", ".owloop/PROMPT_build.md"]
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


@click.group(invoke_without_command=True)
@click.version_option(package_name="owloop")
@click.option("--ascii", is_flag=True, default=False, help="Use ASCII art instead of Unicode glyphs.")
@click.option("--no-color", is_flag=True, default=False, help="Disable colored terminal output.")
@click.option("--compact", is_flag=True, default=False, help="Force the compact single-column TUI layout.")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Show all agent output without folding.")
@click.pass_context
def main(ctx: click.Context, ascii: bool, no_color: bool, compact: bool, verbose: bool) -> None:
    """🦉 owloop — Your code evolves while you sleep."""
    ctx.ensure_object(dict)
    ctx.obj["ascii"] = ascii
    ctx.obj["no_color"] = no_color
    ctx.obj["compact"] = compact
    ctx.obj["verbose"] = verbose
    console = Console(no_color=no_color)

    if ctx.invoked_subcommand is None:
        console.print(_banner_text(ascii=ascii, no_color=no_color))
        console.print(f"[dim]{_brand.TAGLINE}[/]\n")
        console.print("Quick start:")
        console.print('  [bold]owloop go "your goal"[/]  One command: init → spec → run')
        console.print()
        console.print("Commands:")
        console.print("  [bold]owloop go[/]      One-command flow (init + spec + run)")
        console.print("  [bold]owloop spec[/]    Generate specs from a goal")
        console.print("  [bold]owloop run[/]     Start the autonomous loop")
        console.print("  [bold]owloop status[/]  Show current specs and progress")
        console.print("  [bold]owloop report[/]  Generate HTML summary report")
        console.print()
        console.print("[dim]Run[/] [bold]owloop <command> --help[/] [dim]for details.[/]")


@main.command()
@click.argument("goal")
@click.option("--model", default=DEFAULT_MODEL, help="Claude model.", show_default=True)
def go(goal: str, model: str) -> None:
    """One command: init → generate spec(s) → review → start the loop.

    \b
    Example:
        owloop go "refactor error handling in the API layer"
    """
    ascii, no_color, compact, verbose = _cli_options()
    console = Console(no_color=no_color)
    project_dir = Path.cwd()

    console.print()
    console.print(_banner_text(ascii=ascii, no_color=no_color))
    console.print(f"[dim]Goal:[/] {goal}\n")

    _ensure_init(project_dir, console, ascii=ascii)

    adapter = get_adapter(
        "claude",
        model=model,
        claude_cmd=os.environ.get("CLAUDE_CMD", "claude"),
        idle_timeout=3600,
    )
    generator = SpecGenerator(project_dir, adapter)
    stream = AgentStreamDisplay(console, verbose=verbose)

    if verbose:
        console.print(f"  [dim]→ spawning: claude -p --model {model} --permission-mode auto[/]")
        console.print(f"  [dim]→ cwd: {project_dir}[/]")

    try:
        stream.start()
        spec_paths = generator.generate(goal, on_line=stream.on_line)
    except SpecGenerationError as exc:
        console.print(f"\n[red]Error:[/] {exc}")
        raise SystemExit(1) from None
    finally:
        stream.stop()

    console.print()
    console.print(f"[{_brand.GREEN}]✓ {len(spec_paths)} spec(s) generated:[/]")
    for sp in spec_paths:
        console.print(f"  [{_brand.CYAN}]{sp.name}[/]")
    console.print()
    for sp in spec_paths:
        console.print(Panel(
            sp.read_text(encoding="utf-8"),
            title=f"[bold]{sp.name}[/]",
            border_style=_brand.AMBER,
            padding=(1, 2),
        ))

    if sys.stdin.isatty():
        start = Confirm.ask("\nStart the loop now?", default=True, console=console)
    else:
        console.print("\n[dim]Non-interactive: run[/] [bold]owloop run[/] [dim]to start.[/]")
        start = False

    if start:
        console.print(f"\n[{_brand.AMBER}]Starting autonomous loop...[/]")
        _run_engine(
            0, True, model, "claude",
            3600, 0, 0,
            ascii=ascii, no_color=no_color, compact=compact,
        )


@main.command()
@click.option(
    "--example/--no-example",
    default=True,
    help="Create an example spec file.",
    show_default=True,
)
def init(example: bool) -> None:
    """Initialize owloop in the current project.

    Creates a single ``.owloop/`` metadata directory in the project root.
    All specs, logs, and runtime prompts live inside it so the original
    project stays clean.
    """
    ascii, no_color, _compact, verbose = _cli_options()
    console = Console(no_color=no_color)
    cwd = Path.cwd()

    if not (cwd / ".git").exists():
        console.print("[red]Error:[/] Not a git repository. Run [bold]git init[/] first.")
        raise SystemExit(1)

    owloop_path = cwd / ".owloop"
    specs_path = owloop_path / "specs"
    logs_path = owloop_path / "logs"

    created = []

    if not owloop_path.exists():
        owloop_path.mkdir(parents=True)
        created.append(".owloop/")

    if not specs_path.exists():
        specs_path.mkdir(parents=True)
        created.append(".owloop/specs/")

    if not logs_path.exists():
        logs_path.mkdir(parents=True)
        created.append(".owloop/logs/")

    gitignore = cwd / ".gitignore"
    gitignore_entries = [".owloop/logs/", ".owloop/PROMPT_build.md"]
    if gitignore.exists():
        existing = gitignore.read_text(encoding="utf-8")
        to_add = [e for e in gitignore_entries if e not in existing]
        if to_add:
            with open(gitignore, "a", encoding="utf-8") as f:
                f.write("\n# owloop\n")
                for entry in to_add:
                    f.write(f"{entry}\n")
            created.append(".gitignore (updated)")
    else:
        gitignore.write_text("# owloop\n" + "\n".join(gitignore_entries) + "\n", encoding="utf-8")
        created.append(".gitignore")

    if example:
        example_spec = specs_path / "01-example.md"
        if not example_spec.exists():
            example_spec.write_text(
                SPEC_TEMPLATE.format(name="example-task", priority=1),
                encoding="utf-8",
            )
            created.append(".owloop/specs/01-example.md")

    console.print()
    console.print(_banner_text(ascii=ascii, no_color=no_color))

    if created:
        console.print(
            Panel(
                "\n".join(f"  [green]✓[/] {f}" for f in created),
                title="[bold]Initialized[/]",
                border_style=_brand.AMBER,
                padding=(1, 2),
            )
        )
    else:
        console.print("[dim]Already initialized — nothing to create.[/]")

    console.print()
    console.print(f"[bold {_brand.AMBER}]Next steps:[/]")
    console.print("  1. Edit [bold].owloop/specs/01-example.md[/] with your task")
    console.print("  2. Run [bold]owloop run[/]")
    console.print()


@main.command()
@click.argument("goal")
@click.option(
    "--model", default=DEFAULT_MODEL,
    help="Claude model to use (or set CLAUDE_MODEL).", show_default=True,
)
@click.option(
    "--max-rounds", type=int, default=3,
    help="Maximum clarification rounds.", show_default=True,
)
@click.option(
    "--yes", "-y", is_flag=True, default=False,
    help="Approve the generated spec and start the loop immediately.",
)
def spec(goal: str, model: str, max_rounds: int, yes: bool) -> None:
    """Turn a vague goal into a concrete spec via agent clarification.

    Claude scans the codebase, calibrates baselines, and drafts a complete
    constraint-oriented spec. The spec is shown for approval before the loop
    starts unless --yes is passed.
    """
    ascii, no_color, compact, verbose = _cli_options()
    console = Console(no_color=no_color)
    project_dir = Path.cwd()

    _ensure_init(project_dir, console, ascii=ascii)

    console.print()
    console.print(_banner_text(ascii=ascii, no_color=no_color))
    console.print(f"[dim]Goal:[/] {goal}\n")

    adapter = get_adapter(
        "claude",
        model=model,
        claude_cmd=os.environ.get("CLAUDE_CMD", "claude"),
        idle_timeout=3600,
    )
    generator = SpecGenerator(project_dir, adapter)
    stream = AgentStreamDisplay(console, verbose=verbose)

    try:
        stream.start()
        spec_paths = generator.generate(goal, max_rounds=max_rounds, on_line=stream.on_line)
    except SpecGenerationError as exc:
        console.print(f"\n[red]Error:[/] {exc}")
        raise SystemExit(1) from None
    finally:
        stream.stop()

    console.print()
    console.print(f"[{_brand.GREEN}]✓ {len(spec_paths)} spec(s) generated:[/]")
    for sp in spec_paths:
        console.print(f"  [{_brand.CYAN}]{sp}[/]")
    console.print()
    for sp in spec_paths:
        console.print(Panel(
            sp.read_text(encoding="utf-8"),
            title=f"[bold]{sp.name}[/]",
            border_style=_brand.AMBER,
            padding=(1, 2),
        ))

    start_loop = yes
    if not yes:
        if sys.stdin.isatty():
            console.print("\n[bold]Start the loop now?[/] [y/N] ", end="")
            try:
                reply = input().strip().lower() or "n"
            except EOFError:
                reply = "n"
            start_loop = reply.startswith("y")
        else:
            console.print("\n[dim]Non-interactive mode: review the spec and run[/] [bold]owloop run[/]")

    if start_loop:
        console.print(f"\n[{_brand.AMBER}]Starting autonomous loop...[/]")
        _run_engine(
            max_iterations=0, worktree=True, model=model, agent="claude",
            idle_timeout=3600, max_duration=0, max_tokens=0,
            ascii=ascii, no_color=no_color, compact=compact,
        )
    else:
        console.print("\n[dim]Review the spec, then run[/] [bold]owloop run[/]")
    console.print()


STOPPED_REASON_EXIT_1 = {"preflight_failed", "dirty_workspace_declined"}


def _run_engine(
    max_iterations: int, worktree: bool, model: str, agent: str,
    idle_timeout: float = 3600, max_duration: int = 0, max_tokens: int = 0,
    ascii: bool = False, no_color: bool = False, compact: bool = False,
) -> None:
    config = EngineConfig(
        project_dir=Path.cwd(),
        max_iterations=max_iterations,
        max_duration_minutes=max_duration,
        max_tokens=max_tokens,
        idle_timeout=idle_timeout,
        worktree=worktree,
    )
    adapter = get_adapter(
        agent,
        model=model,
        claude_cmd=os.environ.get("CLAUDE_CMD", "claude"),
        idle_timeout=idle_timeout,
    )

    if sys.stdout.isatty():
        tui = OwloopTUI(ascii=ascii, no_color=no_color, compact=compact)

        def _confirm_dirty() -> bool:
            # TUI 已在 setup_worktree() 触发的事件里暂停了 Live 渲染，
            # 这里直接用 rich 的 Confirm 在普通终端上提问即可。
            tui.console.print(
                f"[{_brand.AMBER}]⚠[/] Workspace has uncommitted changes that won't appear in the worktree."
            )
            return Confirm.ask("Continue anyway?", default=False, console=tui.console)

        def _confirm_worktree() -> bool:
            return Confirm.ask(
                "Create an isolated worktree to protect your main repository?",
                default=True,
                console=tui.console,
            )

        config.confirm_dirty = _confirm_dirty
        config.confirm_worktree = _confirm_worktree

        try:
            with tui:
                engine = OwloopEngine(config, adapter, on_event=tui.on_event)
                summary = engine.run()
        except KeyboardInterrupt:
            console = Console(no_color=no_color)
            console.print("\n[dim]owloop stopped.[/]")
            raise SystemExit(0) from None
        tui.print_exit_summary(summary)
    else:
        console = Console(no_color=no_color)
        console.print()
        console.print(_banner_text(ascii=ascii, no_color=no_color))
        console.print(f"[{_brand.AMBER}]Starting autonomous loop...[/]")
        reporter = ConsoleReporter(console, ascii=ascii)
        engine = OwloopEngine(config, adapter, on_event=reporter.on_event)
        try:
            summary = engine.run()
        except KeyboardInterrupt:
            console.print("\n[dim]owloop stopped.[/]")
            raise SystemExit(0) from None
        reporter.print_summary(summary)

    if summary.stopped_reason in STOPPED_REASON_EXIT_1:
        raise SystemExit(1)


def _common_run_options(f: Callable[..., Any]) -> Callable[..., Any]:
    """Shared options for the run command."""
    f = click.option(
        "--agent", type=click.Choice(["claude"]), default="claude",
        help="Coding agent adapter.", show_default=True,
    )(f)
    f = click.option(
        "--model", default=DEFAULT_MODEL,
        help="Claude model to use (or set CLAUDE_MODEL).", show_default=True,
    )(f)
    f = click.option(
        "--idle-timeout", type=float, default=3600,
        help="Kill agent after N seconds without output.", show_default=True,
    )(f)
    f = click.option(
        "--max-duration", type=int, default=0,
        help="Stop loop after N minutes total (0 = unlimited).", show_default=True,
    )(f)
    f = click.option(
        "--max-tokens", type=MaxTokensParamType(), default=0,
        help="Stop loop after N total tokens (0 = unlimited; supports k/w/m shorthand).", show_default=True,
    )(f)
    f = click.option(
        "--worktree/--no-worktree", default=True,
        help="Run in an isolated git worktree.", show_default=True,
    )(f)
    return f


@main.command()
@click.option(
    "--max-iterations", "-n", type=int, default=0,
    help="Maximum iterations (0 = unlimited).", show_default=True,
)
@_common_run_options
def run(max_iterations: int, worktree: bool, model: str, agent: str,
        idle_timeout: float, max_duration: int, max_tokens: int) -> None:
    """Start the autonomous coding loop."""
    ascii, no_color, compact, verbose = _cli_options()
    specs_dir = resolve_specs_dir(Path.cwd())
    if not specs_dir.exists() or not list(specs_dir.glob("*.md")):
        console = Console(no_color=no_color)
        console.print("[red]Error:[/] No specs found. Create specs in [bold].owloop/specs/[/] first.")
        console.print("[dim]Run [bold]owloop init[/] to get started.[/]")
        raise SystemExit(1)

    _run_engine(
        max_iterations, worktree, model, agent,
        idle_timeout, max_duration, max_tokens,
        ascii=ascii, no_color=no_color, compact=compact,
    )


@main.command()
def status() -> None:
    """Show current specs and their completion status."""
    ascii, no_color, _compact, verbose = _cli_options()
    console = Console(no_color=no_color)
    specs_dir = resolve_specs_dir(Path.cwd())

    if not specs_dir.exists():
        console.print("[dim]No specs directory. Run [bold]owloop init[/] first.[/]")
        raise SystemExit(1)

    specs = sorted(specs_dir.glob("*.md"))
    if not specs:
        console.print("[dim]No spec files found in specs/.[/]")
        raise SystemExit(0)

    console.print()
    console.print(_banner_text(ascii=ascii, no_color=no_color))

    from rich.table import Table

    table = Table(
        title="Specs",
        border_style=_brand.AMBER,
        show_lines=False,
        padding=(0, 2),
    )
    table.add_column("", width=3)
    table.add_column("File", style="bold")
    table.add_column("Priority", justify="center")
    table.add_column("Status", justify="center")

    state_display = {
        "done": ("[green]✓[/]", "[green]done[/]"),
        "in_progress": (f"[{_brand.AMBER}]🦉[/]", f"[{_brand.AMBER}]in progress[/]"),
        "pending": ("[dim]○[/]", "[dim]pending[/]"),
    }

    counts = {"done": 0, "in_progress": 0, "pending": 0}

    for spec_file in specs:
        content = spec_file.read_text(encoding="utf-8")
        state = classify_spec(content)
        counts[state] += 1

        priority = "—"
        for line in content.splitlines():
            if line.strip().startswith("## Priority:"):
                priority = line.split(":")[-1].strip()
                break

        icon, status_text = state_display[state]
        table.add_row(icon, spec_file.name, priority, status_text)

    total = len(specs)
    console.print(
        f"  [green]✓ {counts['done']} done[/] · "
        f"[{_brand.AMBER}]🦉 {counts['in_progress']} in progress[/] · "
        f"[dim]○ {counts['pending']} pending[/]"
    )
    console.print(f"  {render_progress_bar(counts['done'], total, ascii=ascii)}")
    console.print()
    console.print(table)
    console.print()


@main.command()
def version() -> None:
    """Show the owloop version."""
    ascii, no_color, _compact, verbose = _cli_options()
    console = Console(no_color=no_color)
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as pkg_version

    try:
        v = pkg_version("owloop")
    except PackageNotFoundError:
        v = "0.0.0-dev"

    console.print()
    console.print(_banner_text(ascii=ascii, no_color=no_color))
    console.print(f"[bold]owloop[/] [{_brand.AMBER}]v{v}[/]")
    console.print()


@main.command()
@click.option("--strict", is_flag=True, help="Treat warnings as errors.")
@click.option(
    "--run-baseline",
    is_flag=True,
    help="Execute baseline commands and verify they run without error.",
)
def check(strict: bool, run_baseline: bool) -> None:
    """Validate all specs before running the loop."""
    ascii, no_color, _compact, verbose = _cli_options()
    console = Console(no_color=no_color)
    specs_dir = resolve_specs_dir(Path.cwd())

    if not specs_dir.is_dir():
        console.print()
        console.print(_banner_text(ascii=ascii, no_color=no_color))
        console.print("[dim]No specs directory. Run [bold]owloop init[/] first.[/]")
        console.print()
        raise SystemExit(0)

    linter = SpecLinter(specs_dir)
    report = linter.lint_all(run_baseline=run_baseline)
    _print_check_report(console, report, ascii=ascii)

    failed = report.error_count > 0 or (strict and report.warning_count > 0)
    if failed:
        raise SystemExit(1)


@main.command()
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output path for the HTML report (default: .lavish/owloop_report.html with --ai).",
)
@click.option(
    "--ai/--no-ai",
    default=True,
    help="Generate AI-powered insights for the report.",
    show_default=True,
)
@click.option(
    "--open",
    "open_report",
    is_flag=True,
    default=False,
    help="Open the report with lavish-axi after generation (requires lavish-axi).",
)
@click.option(
    "--model",
    default=DEFAULT_MODEL,
    help="Claude model to use for AI insights (or set CLAUDE_MODEL).",
    show_default=True,
)
def report(output: Path | None, ai: bool, open_report: bool, model: str) -> None:
    """Generate an HTML summary report for the latest owloop run.

    By default the report includes AI-generated insights (summary, risks,
    review focus) and is styled as a reviewable artifact. Use --no-ai for a
    fast, offline report.
    """
    ascii, no_color, _compact, verbose = _cli_options()
    console = Console(no_color=no_color)
    project_dir = Path.cwd()

    insights = None
    if ai:
        adapter = get_adapter(
            "claude",
            model=model,
            claude_cmd=os.environ.get("CLAUDE_CMD", "claude"),
            idle_timeout=3600,
        )
        ai_generator = AIReportInsightsGenerator(project_dir, adapter)
        stream = AgentStreamDisplay(console, verbose=verbose)

        try:
            stream.start()
            insights = ai_generator.generate(on_line=stream.on_line)
        except FileNotFoundError:
            console.print("[red]Error:[/] No run summary found. Run [bold]owloop run[/] first.")
            raise SystemExit(1) from None
        except RuntimeError as exc:
            console.print(f"[{_brand.AMBER}]⚠ AI insights failed:[/] {exc}")
            console.print("[dim]Falling back to static report. Use --no-ai to skip AI.[/]")
        finally:
            stream.stop()

    if output is None and ai:
        output = project_dir / ".lavish" / "owloop_report.html"

    generator = ReportGenerator(project_dir)
    try:
        report_path = generator.generate(output, insights=insights, use_tailwind=ai)
    except FileNotFoundError:
        console.print("[red]Error:[/] No run summary found. Run [bold]owloop run[/] first.")
        raise SystemExit(1) from None

    if open_report and ai:
        import shutil
        if shutil.which("lavish-axi"):
            console.print(f"[{_brand.AMBER}]Opening report with lavish-axi...[/]")
            subprocess.run(["lavish-axi", str(report_path)], check=False)
        else:
            console.print("[{_brand.AMBER}]⚠ lavish-axi not found:[/] report saved but not opened")

    console.print()
    console.print(_banner_text(ascii=ascii, no_color=no_color))
    console.print(f"[{_brand.GREEN}]✓ Report generated:[/] {report_path}")
    console.print()


@main.command("spec-from-issue")
@click.argument("issue")
@click.option(
    "--repo",
    help="GitHub owner/repo (defaults to the local git remote).",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output path override.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print the spec instead of writing it.",
)
def spec_from_issue(
    issue: str,
    repo: str | None,
    output: Path | None,
    dry_run: bool,
) -> None:
    """Generate a spec draft from a GitHub issue."""
    _ascii, no_color, _compact, _verbose = _cli_options()
    console = Console(no_color=no_color)
    project_dir = Path.cwd()
    converter = IssueToSpecConverter(project_dir)

    try:
        data = converter.from_github(issue, repo=repo)
    except ValueError as exc:
        console.print(f"[red]Error:[/] {exc}")
        raise SystemExit(1) from None
    except RuntimeError as exc:
        console.print(f"[red]Error:[/] {exc}")
        raise SystemExit(1) from None

    if dry_run:
        try:
            rendered = converter.render_spec(data)
        except FileNotFoundError as exc:
            console.print(f"[red]Error:[/] {exc}")
            raise SystemExit(1) from None
        console.print(rendered)
        return

    try:
        spec_path = converter.write_spec(data, output_path=output)
    except FileNotFoundError as exc:
        console.print(f"[red]Error:[/] {exc}")
        raise SystemExit(1) from None

    console.print()
    console.print(f"[{_brand.GREEN}]✓ Spec generated:[/] {spec_path}")
    console.print()


if __name__ == "__main__":
    main()
