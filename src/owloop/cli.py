"""owloop CLI — entry point for uvx owloop / owloop commands."""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from owloop import _brand, git_stats
from owloop.adapters import DEFAULT_IDLE_TIMEOUT, get_adapter
from owloop.backpressure import discover_and_save
from owloop.config import apply_config_defaults, load_run_config
from owloop.engine import EngineConfig, OwloopEngine, RunSummary, TerminalState
from owloop.paths import resolve_logs_dir, resolve_specs_dir
from owloop.report import ReportGenerator
from owloop.report_ai import AIReportInsightsGenerator
from owloop.reporter import ConsoleReporter
from owloop.spec_from_issue import IssueToSpecConverter
from owloop.spec_generator import SpecGenerationError, SpecGenerator
from owloop.spec_linter import LintReport, SpecLinter
from owloop.spec_review import SpecReview
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
The loop re-runs the Acceptance Criteria commands itself and commits only when
they pass — you never commit, push, or mark this spec COMPLETE. Do not edit this
section or the Acceptance Criteria mid-iteration.

Output when complete: `<promise>DONE</promise>`
"""


CHECKED_BOX_RE = re.compile(r"- \[[xX]\]")
# Mirrors the `**Status**: COMPLETE` convention spec_queue._COMPLETE_RE looks for,
# so `owloop status` classifies specs the same way the engine's queue does.
_STATUS_DONE_RE = re.compile(r"^(#{1,3} )?(\*\*)?status(\*\*)?:\s+complete", re.MULTILINE | re.IGNORECASE)
_STATUS_IN_PROGRESS_RE = re.compile(
    r"^(#{1,3} )?(\*\*)?status(\*\*)?:\s+in progress", re.MULTILINE | re.IGNORECASE
)

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
    if _STATUS_DONE_RE.search(content):
        return "done"
    if _STATUS_IN_PROGRESS_RE.search(content):
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


def _run_config_path() -> Path:
    """Return the persistent run configuration file path."""
    return Path.cwd() / ".owloop" / "config.toml"


def _load_and_apply_run_config(**cli_kwargs: Any) -> dict[str, Any]:
    """Load ``.owloop/config.toml`` and merge its ``[run]`` defaults into CLI kwargs."""
    config = load_run_config(_run_config_path())
    return apply_config_defaults(cli_kwargs, config)


def _default_report_path() -> Path:
    """Return the default quick-report output path."""
    return Path.cwd() / ".owloop" / "reports" / "owloop_report_latest.html"


def _generate_quick_report(summary: RunSummary) -> Path | None:
    """Generate a fast, no-AI HTML report and return its path, or None on failure."""
    try:
        report_path = _default_report_path()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        generator = ReportGenerator(summary.main_repo_dir)
        generator.generate(report_path, insights=None, use_tailwind=False)
        return report_path
    except Exception:
        return None


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


def _read_latest_session(project_dir: Path) -> dict[str, Any] | None:
    """Load the latest session descriptor if it exists."""
    path = project_dir / ".owloop" / "logs" / "session_latest.json"
    if not path.is_file():
        return None
    try:
        import json
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _find_worktree_path(project_dir: Path, session: dict[str, Any] | None = None) -> Path | None:
    """Return the worktree path from the session record or ``git worktree list``."""
    if session and session.get("path"):
        return Path(session["path"])
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            wt = Path(line.split(" ", 1)[1])
            if wt != project_dir and wt.name.startswith("owloop-"):
                return wt
    return None


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
        console.print("  [bold]owloop agents[/]  List available coding-agent presets")
        console.print("  [bold]owloop go[/]      One-command flow (init + spec + run)")
        console.print("  [bold]owloop init[/]    Initialize owloop in the current project")
        console.print("  [bold]owloop report[/]  Generate HTML summary report")
        console.print("  [bold]owloop run[/]     Start the autonomous loop")
        console.print("  [bold]owloop spec[/]    Generate specs from a goal")
        console.print("  [bold]owloop status[/]  Show current specs and progress")
        console.print("  [bold]owloop version[/] Show the owloop version")
        console.print()
        console.print("[dim]Run[/] [bold]owloop <command> --help[/] [dim]for details.[/]")


def _validate_agent(ctx: click.Context, param: click.Parameter, value: str) -> str:
    """Validate --agent against builtin + user presets (.owloop/agents.toml)."""
    from owloop.presets import all_presets

    keys = sorted(all_presets(Path.cwd()))
    if value not in keys:
        raise click.BadParameter(f"unknown agent {value!r}. Available: {', '.join(keys)}")
    return value


def _agent_run_options(f: Callable[..., Any]) -> Callable[..., Any]:
    """Shared non-model run options for run, go, and spec."""
    f = click.option(
        "--agent", default="claude", metavar="AGENT", callback=_validate_agent,
        help="Coding agent preset (see `owloop agents` for the full list).",
        show_default=True,
    )(f)
    f = click.option(
        "--verifier-model",
        help="Claude model for the independent verifier agent (defaults to --model).",
        default=None,
    )(f)
    f = click.option(
        "--subagents",
        is_flag=True,
        default=False,
        help="Split large iterations into Orient/Implement/Verify subagent phases.",
    )(f)
    f = click.option(
        "--idle-timeout", type=float, default=DEFAULT_IDLE_TIMEOUT,
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


def _common_run_options(f: Callable[..., Any]) -> Callable[..., Any]:
    """Shared options for the run and go commands (includes --model default None)."""
    f = click.option(
        "--model", default=None, metavar="MODEL",
        help="Model to use (defaults per agent; claude honors CLAUDE_MODEL).",
    )(f)
    return _agent_run_options(f)


def _extra_run_options(f: Callable[..., Any]) -> Callable[..., Any]:
    """Additional run options forwarded by run, go, and spec."""
    f = click.option(
        "--max-iterations", "-n", type=int, default=0,
        help="Maximum iterations (0 = unlimited).", show_default=True,
    )(f)
    f = click.option(
        "--resume",
        is_flag=True,
        default=False,
        help="Resume the most recent owloop session (reuse its worktree and branch).",
    )(f)
    f = click.option(
        "--dry-run", "--one-shot", "dry_run",
        is_flag=True,
        default=False,
        help="Run exactly one iteration, print a pass/fail report, and skip push "
        "(no committed changes are left behind). Use to validate specs without "
        "burning a full overnight run.",
    )(f)
    f = click.option(
        "--no-tui", "--plain", "no_tui",
        is_flag=True,
        default=False,
        help="Bypass the full-screen TUI and print plain console output, even in a TTY.",
    )(f)
    f = click.option(
        "--max-tokens-per-iteration", type=MaxTokensParamType(), default=0,
        help="Kill a single iteration early if it exceeds N tokens (0 = unlimited; "
        "supports k/w/m shorthand).", show_default=True,
    )(f)
    f = click.option(
        "--max-turns-per-iteration", type=int, default=0,
        help="Forward --max-turns N to `claude -p` so a single iteration is bounded "
        "at the source (0 = unlimited; ignored on CLIs without the flag).",
        show_default=True,
    )(f)
    f = click.option(
        "--max-budget-usd", type=float, default=0.0,
        help="Forward a per-iteration USD budget cap to the CLI when supported "
        "(0 = unlimited).", show_default=True,
    )(f)
    f = click.option(
        "--keep-retrying", is_flag=True, default=False,
        help="Legacy behavior: warn and back off on repeated failures instead of "
        "hard-stopping with a `stalled` terminal state.",
    )(f)
    f = click.option(
        "--rollback/--no-rollback", default=True, show_default=True,
        help="Reset the worktree to the last good commit after a failed iteration "
        "(a discarded-diff patch is saved under .owloop/logs/).",
    )(f)
    f = click.option(
        "--notify-webhook", default=None, metavar="URL",
        help="POST a JSON completion notification to this webhook when the run stops "
        "on an attention-worthy state (or set OWLOOP_NOTIFY_WEBHOOK).",
    )(f)
    f = click.option(
        "--notify-desktop", is_flag=True, default=False,
        help="Fire a native desktop notification when the run stops.",
    )(f)
    f = click.option(
        "--converge", "converge_sweeps", type=int, default=0, metavar="N",
        help="After the spec queue empties, run up to N audit sweeps that append gap "
        "specs until the codebase converges on the goal (0 = disabled).",
        show_default=True,
    )(f)
    f = click.option(
        "--workers", type=int, default=1, metavar="N",
        help="Run up to N file-disjoint specs concurrently, each in its own worktree "
        "(1 = sequential). Specs need a `## Files` scope to be scheduled in parallel.",
        show_default=True,
    )(f)
    return f


@main.command()
@click.argument("goal")
@click.option(
    "--verbose", "-v", is_flag=True, default=False,
    help="Show the full spec panel instead of the compact table.",
)
@_extra_run_options
@_common_run_options
def go(
    goal: str,
    agent: str,
    model: str,
    verifier_model: str | None,
    subagents: bool,
    idle_timeout: float,
    max_duration: int,
    max_tokens: int,
    worktree: bool,
    max_iterations: int,
    resume: bool,
    dry_run: bool,
    no_tui: bool,
    max_tokens_per_iteration: int,
    max_turns_per_iteration: int,
    max_budget_usd: float,
    keep_retrying: bool,
    rollback: bool,
    notify_webhook: str | None,
    notify_desktop: bool,
    converge_sweeps: int,
    workers: int,
    verbose: bool,
) -> None:
    """One command: init → generate spec(s) → review → start the loop.

    \b
    Example:
        owloop go "refactor error handling in the API layer"
    """
    ascii, no_color, compact, cli_verbose = _cli_options()
    verbose = verbose or cli_verbose
    console = Console(no_color=no_color)
    project_dir = Path.cwd()

    console.print()
    console.print(_banner_text(ascii=ascii, no_color=no_color))
    console.print(f"[dim]Goal:[/] {goal}\n")

    _ensure_init(project_dir, console, ascii=ascii)

    # Spec generation always runs on Claude Code today; only forward --model
    # when it was meant for Claude, not e.g. a GLM/DeepSeek model id.
    adapter = get_adapter(
        "claude",
        model=model if agent == "claude" else None,
        claude_cmd=os.environ.get("CLAUDE_CMD", "claude"),
        idle_timeout=idle_timeout,
    )
    generator = SpecGenerator(project_dir, adapter)
    stream = AgentStreamDisplay(console, verbose=verbose)

    if verbose:
        console.print(
            f"  [dim]→ spawning: claude -p --model {model or DEFAULT_MODEL} --permission-mode auto[/]"
        )
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

    display = _format_spec_table(spec_paths, verbose=verbose)
    if isinstance(display, Table):
        console.print(display)
    else:
        for panel in display:
            console.print(panel)

    run_kwargs = _load_and_apply_run_config(
        max_iterations=max_iterations,
        worktree=worktree,
        model=model,
        agent=agent,
        idle_timeout=idle_timeout,
        max_duration=max_duration,
        max_tokens=max_tokens,
        ascii=ascii,
        no_color=no_color,
        compact=compact,
        verifier_model=verifier_model,
        subagents=subagents,
        resume=resume,
        no_tui=no_tui,
        dry_run=dry_run,
        max_tokens_per_iteration=max_tokens_per_iteration,
        max_turns_per_iteration=max_turns_per_iteration,
        max_budget_usd=max_budget_usd,
        keep_retrying=keep_retrying,
        rollback=rollback,
        notify_webhook=notify_webhook,
        notify_desktop=notify_desktop,
        converge_sweeps=converge_sweeps,
        workers=workers,
    )

    console.print(f"\n[{_brand.AMBER}]Starting autonomous loop...[/]")
    _run_engine(**run_kwargs)


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
    gitignore_entries = [".owloop/"]
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

    backpressure_path = owloop_path / "backpressure.json"
    if not backpressure_path.exists():
        try:
            _commands, bp_path = discover_and_save(cwd)
            created.append(str(bp_path.relative_to(cwd)))
        except Exception:
            pass

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
    "--model", default=None,
    help="Claude model to use (or set CLAUDE_MODEL).",
)
@click.option(
    "--max-rounds", type=int, default=3,
    help="Maximum clarification rounds.", show_default=True,
)
@click.option(
    "--yes", "-y", is_flag=True, default=False,
    help="Approve the generated spec and start the loop immediately.",
)
@click.option(
    "--verbose", "-v", is_flag=True, default=False,
    help="Show the full spec panel instead of the compact table.",
)
@_extra_run_options
@_agent_run_options
def spec(
    goal: str,
    model: str,
    max_rounds: int,
    yes: bool,
    agent: str,
    verifier_model: str | None,
    subagents: bool,
    idle_timeout: float,
    max_duration: int,
    max_tokens: int,
    worktree: bool,
    max_iterations: int,
    resume: bool,
    dry_run: bool,
    no_tui: bool,
    max_tokens_per_iteration: int,
    max_turns_per_iteration: int,
    max_budget_usd: float,
    keep_retrying: bool,
    rollback: bool,
    notify_webhook: str | None,
    notify_desktop: bool,
    converge_sweeps: int,
    workers: int,
    verbose: bool,
) -> None:
    """Turn a vague goal into a concrete spec via agent clarification.

    Claude scans the codebase, calibrates baselines, and drafts a complete
    constraint-oriented spec. The spec is shown for approval before the loop
    starts unless --yes is passed.
    """
    ascii, no_color, compact, cli_verbose = _cli_options()
    verbose = verbose or cli_verbose
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
        idle_timeout=idle_timeout,
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

    display = _format_spec_table(spec_paths, verbose=verbose)
    if isinstance(display, Table):
        console.print(display)
    else:
        for panel in display:
            console.print(panel)

    run_kwargs = _load_and_apply_run_config(
        max_iterations=max_iterations,
        worktree=worktree,
        model=model,
        agent=agent,
        idle_timeout=idle_timeout,
        max_duration=max_duration,
        max_tokens=max_tokens,
        ascii=ascii,
        no_color=no_color,
        compact=compact,
        verifier_model=verifier_model,
        subagents=subagents,
        resume=resume,
        no_tui=no_tui,
        dry_run=dry_run,
        max_tokens_per_iteration=max_tokens_per_iteration,
        max_turns_per_iteration=max_turns_per_iteration,
        max_budget_usd=max_budget_usd,
        keep_retrying=keep_retrying,
        rollback=rollback,
        notify_webhook=notify_webhook,
        notify_desktop=notify_desktop,
        converge_sweeps=converge_sweeps,
        workers=workers,
    )

    start_loop = yes
    if not yes:
        if sys.stdin.isatty():
            console.print("\n[bold]Start the loop now?[/] [Y/n] ", end="")
            try:
                reply = input().strip().lower() or "y"
            except EOFError:
                reply = "y"
            start_loop = reply.startswith("y")
        else:
            console.print("\n[dim]Non-interactive mode: review the spec and run[/] [bold]owloop run[/]")

    if start_loop:
        console.print(f"\n[{_brand.AMBER}]Starting autonomous loop...[/]")
        _run_engine(**run_kwargs)
    else:
        console.print("\n[dim]Review the spec, then run[/] [bold]owloop run[/]")
    console.print()


@main.command()
def agents() -> None:
    """List available coding-agent presets and whether they're ready to use.

    Two integration paths exist: native adapters (claude, kimi) and ACP —
    the Agent Client Protocol (https://agentclientprotocol.com) — which
    covers every other preset with a single implementation. Add your own
    ACP agents in ``.owloop/agents.toml``.
    """
    import shutil as _shutil

    from rich.table import Table

    from owloop.presets import all_presets

    _ascii, no_color, _compact, _verbose = _cli_options()
    console = Console(no_color=no_color)

    table = Table(border_style=_brand.AMBER, header_style=f"bold {_brand.AMBER}")
    table.add_column("agent")
    table.add_column("kind")
    table.add_column("command")
    table.add_column("model")
    table.add_column("status")

    for key, preset in sorted(all_presets(Path.cwd()).items()):
        binary = preset.cmd[0]
        problems: list[str] = []
        if not _shutil.which(binary):
            problems.append(f"{binary} not found")
        missing = [v for v in preset.required_env_vars() if os.environ.get(v) is None]
        if missing:
            problems.append(f"set {', '.join(missing)}")
        status = f"[red]✗ {'; '.join(problems)}[/]" if problems else f"[{_brand.GREEN}]✓ ready[/]"
        if preset.experimental and not problems:
            status += " [dim](experimental)[/]"
        table.add_row(
            f"[bold]{key}[/]",
            preset.kind,
            " ".join(preset.cmd),
            preset.default_model or "[dim]agent default[/]",
            status,
        )

    console.print(table)
    console.print(
        "[dim]Use with[/] [bold]owloop run --agent <agent>[/]"
        "[dim]; define custom agents in .owloop/agents.toml[/]"
    )


# Three-tier exit codes for unattended callers (CI, cron, wrappers).
#   0 = finished successfully
#   1 = hard failure (engine/agent broke, spec tampered, preflight failed)
#   2 = needs human attention (blocked, decide, stalled, exhausted, interrupted)
_EXIT_CODE_MAP = {
    TerminalState.SUCCESS: 0,
    TerminalState.CLEAN_NO_OP: 0,
    TerminalState.BLOCKED: 2,
    TerminalState.DECIDE: 2,
    TerminalState.STALLED: 2,
    TerminalState.EXHAUSTED: 2,
    TerminalState.TAMPERED: 1,
    TerminalState.INTERRUPTED: 2,
    TerminalState.FAILED: 1,
}


def _exit_code_for_summary(summary: RunSummary) -> int:
    return _EXIT_CODE_MAP.get(cast(TerminalState, summary.state), 1)


def _run_engine(
    max_iterations: int, worktree: bool, model: str | None, agent: str,
    idle_timeout: float = DEFAULT_IDLE_TIMEOUT, max_duration: int = 0, max_tokens: int = 0,
    ascii: bool = False, no_color: bool = False, compact: bool = False,
    verifier_model: str | None = None, subagents: bool = False,
    session_id: str | None = None, resume: bool = False,
    no_tui: bool = False, dry_run: bool = False,
    max_tokens_per_iteration: int = 0,
    max_turns_per_iteration: int = 0,
    max_budget_usd: float = 0.0,
    keep_retrying: bool = False,
    rollback: bool = True,
    notify_webhook: str | None = None,
    notify_desktop: bool = False,
    converge_sweeps: int = 0,
    workers: int = 1,
) -> None:
    # Merge persistent config defaults before constructing the engine.
    kwargs = _load_and_apply_run_config(
        max_iterations=max_iterations,
        worktree=worktree,
        model=model,
        agent=agent,
        idle_timeout=idle_timeout,
        max_duration=max_duration,
        max_tokens=max_tokens,
        ascii=ascii,
        no_color=no_color,
        compact=compact,
        verifier_model=verifier_model,
        subagents=subagents,
        session_id=session_id,
        resume=resume,
        no_tui=no_tui,
        dry_run=dry_run,
        max_tokens_per_iteration=max_tokens_per_iteration,
        max_turns_per_iteration=max_turns_per_iteration,
        max_budget_usd=max_budget_usd,
        keep_retrying=keep_retrying,
        rollback=rollback,
        notify_webhook=notify_webhook,
        notify_desktop=notify_desktop,
        converge_sweeps=converge_sweeps,
        workers=workers,
    )
    max_iterations = kwargs["max_iterations"]
    worktree = kwargs["worktree"]
    model = kwargs["model"]
    agent = kwargs["agent"]
    idle_timeout = kwargs["idle_timeout"]
    max_duration = kwargs["max_duration"]
    max_tokens = kwargs["max_tokens"]
    ascii = kwargs["ascii"]
    no_color = kwargs["no_color"]
    compact = kwargs["compact"]
    verifier_model = kwargs["verifier_model"]
    subagents = kwargs["subagents"]
    session_id = kwargs["session_id"]
    resume = kwargs["resume"]
    no_tui = kwargs["no_tui"]
    dry_run = kwargs["dry_run"]
    max_tokens_per_iteration = kwargs["max_tokens_per_iteration"]
    max_turns_per_iteration = kwargs["max_turns_per_iteration"]
    max_budget_usd = kwargs["max_budget_usd"]
    keep_retrying = kwargs["keep_retrying"]
    rollback = kwargs["rollback"]
    notify_webhook = kwargs["notify_webhook"]
    notify_desktop = kwargs["notify_desktop"]
    converge_sweeps = kwargs["converge_sweeps"]
    workers = kwargs["workers"]

    resolved_webhook = notify_webhook or os.environ.get("OWLOOP_NOTIFY_WEBHOOK") or None
    if workers > 1:
        _run_parallel(
            workers=workers, model=model, agent=agent, idle_timeout=idle_timeout,
            ascii=ascii, no_color=no_color,
            notify_webhook=resolved_webhook, notify_desktop=notify_desktop,
        )
        return
    config = EngineConfig(
        project_dir=Path.cwd(),
        max_iterations=max_iterations,
        max_duration_minutes=max_duration,
        max_tokens=max_tokens,
        max_tokens_per_iteration=max_tokens_per_iteration,
        idle_timeout=idle_timeout,
        worktree=worktree,
        use_subagents=subagents,
        session_id=session_id,
        resume=resume,
        dry_run=dry_run,
        keep_retrying=keep_retrying,
        rollback=rollback,
        notify_webhook=resolved_webhook,
        notify_desktop=notify_desktop,
        converge_sweeps=converge_sweeps,
    )
    adapter = get_adapter(
        agent,
        model=model,
        claude_cmd=os.environ.get("CLAUDE_CMD", "claude"),
        kimi_cmd=os.environ.get("KIMI_CMD", "kimi"),
        idle_timeout=idle_timeout,
        max_turns=max_turns_per_iteration or None,
        max_budget_usd=max_budget_usd or None,
        project_dir=Path.cwd(),
    )

    if verifier_model:
        config.verifier_adapter = get_adapter(
            agent,
            model=verifier_model,
            claude_cmd=os.environ.get("CLAUDE_CMD", "claude"),
            kimi_cmd=os.environ.get("KIMI_CMD", "kimi"),
            idle_timeout=idle_timeout,
            project_dir=Path.cwd(),
        )

    report_path: Path | None = None

    if not no_tui and sys.stdout.isatty():
        tui = OwloopTUI(ascii=ascii, no_color=no_color, compact=compact)

        try:
            with tui:
                engine = OwloopEngine(config, adapter, on_event=tui.on_event)
                summary = engine.run()
        except KeyboardInterrupt:
            console = Console(no_color=no_color)
            console.print("\n[dim]owloop stopped.[/]")
            raise SystemExit(0) from None
        if summary.iterations > 0 and not config.dry_run:
            report_path = _generate_quick_report(summary)
        tui.print_exit_summary(summary, report_path=str(report_path) if report_path else None)
        if config.dry_run:
            _print_dry_run_report(tui.console, summary)
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
        if summary.iterations > 0 and not config.dry_run:
            report_path = _generate_quick_report(summary)
        reporter.print_summary(summary, report_path=str(report_path) if report_path else None)
        if config.dry_run:
            _print_dry_run_report(console, summary)
        if report_path:
            console.print(f"Report: {report_path}")

    exit_code = _exit_code_for_summary(summary)
    if exit_code:
        raise SystemExit(exit_code)



def _run_parallel(
    *, workers: int, model: str | None, agent: str, idle_timeout: float,
    ascii: bool, no_color: bool,
    notify_webhook: str | None, notify_desktop: bool,
) -> None:
    """Run the file-disjoint parallel worker mode (`owloop run --workers N`)."""
    from owloop.parallel import ParallelConfig, ParallelOrchestrator

    console = Console(no_color=no_color)
    console.print()
    console.print(_banner_text(ascii=ascii, no_color=no_color))
    console.print(f"[{_brand.AMBER}]Starting {workers} parallel workers...[/]")

    def _adapter_factory() -> Any:
        # Fresh adapter per worker: adapters hold per-run streaming state, so
        # concurrent workers must not share one instance.
        return get_adapter(
            agent, model=model,
            claude_cmd=os.environ.get("CLAUDE_CMD", "claude"),
            kimi_cmd=os.environ.get("KIMI_CMD", "kimi"),
            idle_timeout=idle_timeout,
        )

    config = ParallelConfig(
        project_dir=Path.cwd(),
        workers=workers,
        notify_webhook=notify_webhook,
        notify_desktop=notify_desktop,
    )
    reporter = ConsoleReporter(console, ascii=ascii)
    orchestrator = ParallelOrchestrator(config, _adapter_factory, on_event=reporter.on_event)
    try:
        summary = orchestrator.run()
    except KeyboardInterrupt:
        console.print("\n[dim]owloop stopped.[/]")
        raise SystemExit(0) from None
    reporter.print_summary(summary)
    exit_code = _exit_code_for_summary(summary)
    if exit_code:
        raise SystemExit(exit_code)


def _print_dry_run_report(console: Console, summary: RunSummary) -> None:
    """Print the concise pass/fail report produced by ``--dry-run`` / ``--one-shot``."""
    report = summary.dry_run_report
    if report is None:
        return

    promise_line = (
        f"[{_brand.GREEN}]<promise>DONE</promise> emitted[/]"
        if report.promise_done
        else f"[{_brand.RED}]<promise>DONE</promise> not emitted[/]"
    )
    lines = [promise_line]
    if report.spec_name:
        lines.append(f"Spec: {report.spec_name}")
    lines.append(
        f"Acceptance criteria: [{_brand.GREEN}]{report.acceptance_passed} passed[/] / "
        f"[{_brand.RED}]{report.acceptance_failed} failed[/]"
    )
    lines.append(f"Tokens used: {report.tokens_used}")

    console.print()
    console.print(
        Panel(
            "\n".join(lines),
            title="[bold]Dry-run report[/]",
            border_style=_brand.AMBER,
            padding=(1, 2),
        )
    )


@main.command()
@click.option(
    "--max-iterations", "-n", type=int, default=0,
    help="Maximum iterations (0 = unlimited).", show_default=True,
)
@click.option(
    "--resume",
    is_flag=True,
    default=False,
    help="Resume the most recent owloop session (reuse its worktree and branch).",
)
@click.option(
    "--dry-run", "--one-shot", "dry_run",
    is_flag=True,
    default=False,
    help="Run exactly one iteration, print a pass/fail report, and skip push "
    "(no committed changes are left behind). Use to validate specs without "
    "burning a full overnight run.",
)
@click.option(
    "--no-tui", "--plain", "no_tui",
    is_flag=True,
    default=False,
    help="Bypass the full-screen TUI and print plain console output, even in a TTY.",
)
@click.option(
    "--max-tokens-per-iteration", type=MaxTokensParamType(), default=0,
    help="Kill a single iteration early if it exceeds N tokens (0 = unlimited; "
    "supports k/w/m shorthand).", show_default=True,
)
@click.option(
    "--max-turns-per-iteration", type=int, default=0,
    help="Forward --max-turns N to `claude -p` so a single iteration is bounded "
    "at the source (0 = unlimited; ignored on CLIs without the flag).",
    show_default=True,
)
@click.option(
    "--max-budget-usd", type=float, default=0.0,
    help="Forward a per-iteration USD budget cap to the CLI when supported "
    "(0 = unlimited).", show_default=True,
)
@click.option(
    "--keep-retrying", is_flag=True, default=False,
    help="Legacy behavior: warn and back off on repeated failures instead of "
    "hard-stopping with a `stalled` terminal state.",
)
@click.option(
    "--rollback/--no-rollback", default=True, show_default=True,
    help="Reset the worktree to the last good commit after a failed iteration "
    "(a discarded-diff patch is saved under .owloop/logs/).",
)
@click.option(
    "--notify-webhook", default=None, metavar="URL",
    help="POST a JSON completion notification to this webhook when the run stops "
    "on an attention-worthy state (or set OWLOOP_NOTIFY_WEBHOOK).",
)
@click.option(
    "--notify-desktop", is_flag=True, default=False,
    help="Fire a native desktop notification when the run stops.",
)
@click.option(
    "--converge", "converge_sweeps", type=int, default=0, metavar="N",
    help="After the spec queue empties, run up to N audit sweeps that append gap "
    "specs until the codebase converges on the goal (0 = disabled).",
    show_default=True,
)
@click.option(
    "--workers", type=int, default=1, metavar="N",
    help="Run up to N file-disjoint specs concurrently, each in its own worktree "
    "(1 = sequential). Specs need a `## Files` scope to be scheduled in parallel.",
    show_default=True,
)
@_common_run_options
def run(max_iterations: int, resume: bool, dry_run: bool, no_tui: bool, max_tokens_per_iteration: int,
        max_turns_per_iteration: int, max_budget_usd: float, keep_retrying: bool, rollback: bool,
        notify_webhook: str | None, notify_desktop: bool, converge_sweeps: int, workers: int,
        worktree: bool, model: str, agent: str, verifier_model: str | None, subagents: bool,
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
        verifier_model=verifier_model,
        subagents=subagents,
        resume=resume,
        no_tui=no_tui,
        dry_run=dry_run,
        max_tokens_per_iteration=max_tokens_per_iteration,
        max_turns_per_iteration=max_turns_per_iteration,
        max_budget_usd=max_budget_usd,
        keep_retrying=keep_retrying,
        rollback=rollback,
        notify_webhook=notify_webhook,
        notify_desktop=notify_desktop,
        converge_sweeps=converge_sweeps,
        workers=workers,
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

    # Runtime section
    session = _read_latest_session(Path.cwd())
    if session:
        from rich.table import Table as RuntimeTable

        runtime = RuntimeTable(
            title="Runtime",
            border_style=_brand.AMBER,
            show_lines=False,
            padding=(0, 2),
        )
        runtime.add_column("Key", style="bold")
        runtime.add_column("Value")

        session_id = session.get("session_id", "—")
        branch = session.get("branch", "—")
        session_status = session.get("status", "—")
        stopped_reason = session.get("stopped_reason", session.get("status", "—"))
        wt_path = _find_worktree_path(Path.cwd(), session) or Path("—")
        resumable = session_status in ("running",) or stopped_reason in {
            "interrupted", "stalled", "exhausted", "max_iterations_reached",
            "max_duration_reached", "max_tokens_reached", "idle_timeout",
        }
        runtime.add_row("Session", str(session_id))
        runtime.add_row("Branch", str(branch))
        runtime.add_row("Worktree", str(wt_path))
        runtime.add_row("Stopped reason", str(stopped_reason))
        runtime.add_row("Resumable", "yes" if resumable else "no")
        runtime.add_row("Iterations", str(session.get("iterations", "—")))
        runtime.add_row("Tokens used", str(session.get("tokens_used", "—")))
        console.print(runtime)
        console.print()


@main.command()
@click.option(
    "--auto",
    is_flag=True,
    default=False,
    help="Automatically merge, push, and clean up the owloop session.",
)
def finish(auto: bool) -> None:
    """Show the latest owloop session and optionally merge/push/cleanup."""
    ascii, no_color, _compact, _verbose = _cli_options()
    console = Console(no_color=no_color)
    project_dir = Path.cwd()

    session = _read_latest_session(project_dir)
    if not session:
        console.print("[red]Error:[/] No latest session found. Run [bold]owloop run[/] first.")
        raise SystemExit(1)

    session_id = session.get("session_id", "—")
    branch = session.get("branch", "—")
    wt_path = _find_worktree_path(project_dir, session)
    stopped_reason = session.get("stopped_reason", session.get("status", "—"))
    iterations = session.get("iterations", 0)

    console.print()
    console.print(_banner_text(ascii=ascii, no_color=no_color))

    table = Table(
        title="Latest owloop session",
        border_style=_brand.AMBER,
        show_lines=False,
        padding=(0, 2),
    )
    table.add_column("Key", style="bold")
    table.add_column("Value")
    table.add_row("Session", str(session_id))
    table.add_row("Branch", str(branch))
    table.add_row("Worktree", str(wt_path) if wt_path else "—")
    table.add_row("Stopped reason", str(stopped_reason))
    table.add_row("Iterations", str(iterations))
    console.print(table)
    console.print()

    # Diff summary
    cwd = wt_path if wt_path and wt_path.is_dir() and branch.startswith("owloop/") else project_dir
    commits = git_stats.get_recent_commits(cwd, iterations)
    total_files, total_ins, total_del = git_stats.total_diff_stats(commits)
    console.print(
        f"Diff: {total_files} files · [green]+{total_ins}[/] · [red]-{total_del}[/]"
    )
    for commit in commits:
        console.print(f"  [cyan]{commit.hash}[/] {commit.message}")
    console.print()

    report_path = _default_report_path()
    if report_path.exists():
        console.print(f"Report: {report_path}")
    else:
        console.print("Report: not generated")
    console.print()

    # Base branch detection
    base_branch = "main"
    for candidate in ("main", "master"):
        result = subprocess.run(
            ["git", "show-ref", "--verify", f"refs/heads/{candidate}"],
            cwd=project_dir,
            capture_output=True,
        )
        if result.returncode == 0:
            base_branch = candidate
            break

    console.print(f"[{_brand.AMBER}]Next steps:[/]")
    console.print(f"  review:  git -C {project_dir} log --oneline {base_branch}..{branch}")
    console.print(f"  merge:   git -C {project_dir} checkout {base_branch} && git merge {branch}")
    console.print(f"  push:    git -C {project_dir} push origin {base_branch}")
    if wt_path:
        console.print(f"  cleanup: git -C {project_dir} worktree remove {wt_path} && git -C {project_dir} branch -d {branch}")
    console.print("  resume:  owloop run --resume")
    console.print()

    if not auto:
        return

    # Auto mode: merge, push, remove worktree, delete branch. Stop on first failure.
    console.print(f"[{_brand.AMBER}]Auto-finishing session...[/]")

    def _git_step(desc: str, cwd: Path, *args: str) -> bool:
        console.print(f"  {desc} ...", end=" ")
        result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
        if result.returncode != 0:
            console.print(f"[red]failed[/]\n{result.stderr.strip()}")
            return False
        console.print(f"[{_brand.GREEN}]ok[/]")
        return True

    # Idempotent merge: skip if already merged.
    merge_check = subprocess.run(
        ["git", "merge-base", "--is-ancestor", branch, base_branch],
        cwd=project_dir,
        capture_output=True,
    )
    already_merged = merge_check.returncode == 0

    if not already_merged:
        if not _git_step(f"checkout {base_branch}", project_dir, "checkout", base_branch):
            raise SystemExit(1)
        if not _git_step(f"merge {branch}", project_dir, "merge", "--no-ff", branch, "-m", f"owloop: merge {branch}"):
            raise SystemExit(1)
    else:
        console.print(f"  [dim]{branch} already merged into {base_branch}[/]")

    if not _git_step("push", project_dir, "push", "origin", base_branch):
        raise SystemExit(1)

    if wt_path and wt_path.exists():
        # Remove worktree if it exists.
        subprocess.run(["git", "worktree", "remove", "--force", str(wt_path)], cwd=project_dir, capture_output=True)
        if wt_path.exists():
            shutil.rmtree(wt_path, ignore_errors=True)

    # Delete branch if it still exists.
    branch_exists = subprocess.run(
        ["git", "show-ref", "--verify", f"refs/heads/{branch.split('/', 1)[1]}"],
        cwd=project_dir,
        capture_output=True,
    ).returncode == 0
    if branch_exists:
        short_branch = branch.split("/", 1)[1]
        if not _git_step(f"delete branch {short_branch}", project_dir, "branch", "-d", short_branch):
            raise SystemExit(1)

    console.print(f"[{_brand.GREEN}]✓ Session finished.[/]")
    console.print()


@main.command()
@click.option("--iter", "iter_n", type=int, default=None, help="Show the log for iteration N.")
@click.option("--events", is_flag=True, default=False, help="Show the last 50 events from events.jsonl.")
@click.option("--patch", is_flag=True, default=False, help="Show the latest discarded patch.")
def logs(iter_n: int | None, events: bool, patch: bool) -> None:
    """Inspect owloop log files."""
    ascii, no_color, _compact, _verbose = _cli_options()
    console = Console(no_color=no_color)
    logs_dir = resolve_logs_dir(Path.cwd())

    if not logs_dir.exists():
        console.print("[red]Error:[/] No logs directory. Run [bold]owloop run[/] first.")
        raise SystemExit(1)

    if patch:
        patches = sorted(logs_dir.glob("iter_*_discarded.patch"))
        if not patches:
            console.print("[dim]No discarded patches found.[/]")
            raise SystemExit(0)
        latest = patches[-1]
        console.print(latest.read_text(encoding="utf-8"))
        raise SystemExit(0)

    if events:
        events_path = logs_dir / "events.jsonl"
        if not events_path.is_file():
            console.print("[red]Error:[/] events.jsonl not found.")
            raise SystemExit(1)
        lines = events_path.read_text(encoding="utf-8").splitlines()
        for line in lines[-50:]:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                ts = record.get("ts", "—")
                kind = record.get("kind", "—")
                data = record.get("data", {})
                console.print(f"[{ts}] {kind}: {data}")
            except json.JSONDecodeError:
                console.print(line)
        raise SystemExit(0)

    if iter_n is not None:
        candidates = [p for p in logs_dir.glob("iter_*.log") if str(iter_n) in p.name]
        if not candidates:
            console.print(f"[red]Error:[/] No log found for iteration {iter_n}.")
            raise SystemExit(1)
        target = sorted(candidates)[-1]
        console.print(target.read_text(encoding="utf-8"))
        raise SystemExit(0)

    # Default: latest iteration log
    log_files = sorted(logs_dir.glob("iter_*.log"))
    if not log_files:
        console.print("[dim]No iteration logs found.[/]")
        raise SystemExit(0)
    latest = log_files[-1]
    console.print(latest.read_text(encoding="utf-8"))


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
def discover() -> None:
    """Discover and save project verification commands."""
    ascii, no_color, _compact, verbose = _cli_options()
    console = Console(no_color=no_color)
    cwd = Path.cwd()

    try:
        commands, path = discover_and_save(cwd)
    except Exception as exc:
        console.print(f"[red]Error:[/] failed to discover backpressure commands: {exc}")
        raise SystemExit(1) from None

    console.print()
    console.print(_banner_text(ascii=ascii, no_color=no_color))
    console.print(f"[bold]owloop[/] [{_brand.AMBER}]discover[/]")
    console.print()

    if commands:
        console.print(f"[green]✓ {len(commands)} command(s) discovered:[/]")
        for cmd in commands:
            console.print(f"  [{_brand.CYAN}]{cmd.name}[/]: {cmd.command} [{_brand.GRAY}]{cmd.source}[/]")
    else:
        console.print("[dim]No verification commands discovered.[/]")

    console.print(f"[dim]Saved to[/] {path}")
    console.print()


@main.command()
@click.option("--strict", is_flag=True, help="Treat warnings as errors.")
@click.option(
    "--run-baseline",
    is_flag=True,
    help="Execute baseline commands and verify they run without error.",
)
@click.option(
    "--review",
    is_flag=True,
    help="Run static, executable, and agent review on each spec.",
)
def check(strict: bool, run_baseline: bool, review: bool) -> None:
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

    if review:
        project_dir = specs_dir.parent
        reviewer = SpecReview(specs_dir, project_dir=project_dir)
        has_errors = False
        has_warnings = False
        for spec_file in sorted(specs_dir.glob("*.md")):
            report = reviewer.review(spec_file, auto_fix=True)
            console.print(f"\n[bold]Review:[/] {spec_file.name}")
            if report.auto_fixed:
                console.print(f"  [green]✓ auto-fixed {len(report.auto_fixed)} issue(s)[/]")
            for finding in report.findings:
                icon = "✗" if finding.severity == "error" else "⚠"
                color = _brand.RED if finding.severity == "error" else _brand.AMBER
                console.print(f"  [{color}]{icon}[/] {finding.message}")
                if finding.severity == "error":
                    has_errors = True
                else:
                    has_warnings = True
        if has_errors or (strict and has_warnings):
            raise SystemExit(1)
        return

    linter = SpecLinter(specs_dir)
    lint_report = linter.lint_all(run_baseline=run_baseline)
    _print_check_report(console, lint_report, ascii=ascii)

    failed = lint_report.error_count > 0 or (strict and lint_report.warning_count > 0)
    if failed:
        raise SystemExit(1)


@main.command()
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output path for the HTML report (default: .owloop/reports/owloop_report.html with --ai).",

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
            idle_timeout=DEFAULT_IDLE_TIMEOUT,
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
        output = project_dir / ".owloop" / "reports" / "owloop_report.html"

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
    ascii, no_color, _compact, _verbose = _cli_options()
    console = Console(no_color=no_color)
    project_dir = Path.cwd()

    _ensure_init(project_dir, console, ascii=ascii)

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

    if sys.stdin.isatty() and not dry_run:
        console.print("\n[bold]Run owloop check on this spec?[/] [y/N] ", end="")
        try:
            reply = input().strip().lower() or "n"
        except EOFError:
            reply = "n"
        if reply.startswith("y"):
            subprocess.run([sys.argv[0], "check"], cwd=project_dir)
            return

        console.print("\n[bold]Start owloop run now?[/] [y/N] ", end="")
        try:
            reply = input().strip().lower() or "n"
        except EOFError:
            reply = "n"
        if reply.startswith("y"):
            subprocess.run([sys.argv[0], "run"], cwd=project_dir)


if __name__ == "__main__":
    main()
