"""owloop CLI — entry point for uvx owloop / owloop commands."""

import os
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from owloop import _brand
from owloop.adapters import get_adapter
from owloop.engine import EngineConfig, OwloopEngine
from owloop.report import ReportGenerator
from owloop.reporter import ConsoleReporter
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
    """Return the owloop banner using brand owl art."""
    art = _brand.ASCII_OWL_SMALL if ascii else _brand.OWL_SMALL
    lines = list(art)
    # Place the product name next to the owl's eyes.
    if len(lines) > 1:
        lines[1] = f"{lines[1]}   owloop"
    joined = "\n".join(lines)
    if ascii and no_color:
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


def _cli_options() -> tuple[bool, bool, bool]:
    """Read global --ascii / --no-color / --compact flags from the current Click context."""
    ctx = click.get_current_context()
    obj = ctx.ensure_object(dict)
    return bool(obj.get("ascii")), bool(obj.get("no_color")), bool(obj.get("compact"))


@click.group(invoke_without_command=True)
@click.version_option(package_name="owloop")
@click.option("--ascii", is_flag=True, default=False, help="Use ASCII art instead of Unicode glyphs.")
@click.option("--no-color", is_flag=True, default=False, help="Disable colored terminal output.")
@click.option("--compact", is_flag=True, default=False, help="Force the compact single-column TUI layout.")
@click.pass_context
def main(ctx: click.Context, ascii: bool, no_color: bool, compact: bool) -> None:
    """🦉 owloop — Your code evolves while you sleep."""
    ctx.ensure_object(dict)
    ctx.obj["ascii"] = ascii
    ctx.obj["no_color"] = no_color
    ctx.obj["compact"] = compact
    console = Console(no_color=no_color)

    if ctx.invoked_subcommand is None:
        console.print(_banner_text(ascii=ascii, no_color=no_color))
        console.print(f"[dim]{_brand.TAGLINE}[/]\n")
        console.print("Commands:")
        console.print("  [bold]owloop init[/]    Initialize owloop in current project")
        console.print("  [bold]owloop run[/]     Start the autonomous loop")
        console.print("  [bold]owloop plan[/]    Generate implementation plan from specs")
        console.print("  [bold]owloop status[/]  Show current specs and progress")
        console.print("  [bold]owloop version[/] Show installed version")
        console.print()
        console.print("[dim]Run[/] [bold]owloop <command> --help[/] [dim]for details.[/]")


@main.command()
@click.option(
    "--specs-dir",
    default="specs",
    help="Directory for spec files.",
    show_default=True,
)
@click.option(
    "--example/--no-example",
    default=True,
    help="Create an example spec file.",
    show_default=True,
)
def init(specs_dir: str, example: bool) -> None:
    """Initialize owloop in the current project."""
    ascii, no_color, _compact = _cli_options()
    console = Console(no_color=no_color)
    cwd = Path.cwd()

    if not (cwd / ".git").exists():
        console.print("[red]Error:[/] Not a git repository. Run [bold]git init[/] first.")
        raise SystemExit(1)

    specs_path = cwd / specs_dir
    logs_path = cwd / "logs"

    created = []

    if not specs_path.exists():
        specs_path.mkdir(parents=True)
        created.append(f"{specs_dir}/")

    if not logs_path.exists():
        logs_path.mkdir(parents=True)
        created.append("logs/")

    gitignore = cwd / ".gitignore"
    gitignore_entries = ["logs/", "PROMPT_build.md", "PROMPT_plan.md"]
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
            created.append(f"{specs_dir}/01-example.md")

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
    console.print(f"  1. Edit [bold]{specs_dir}/01-example.md[/] with your task")
    console.print("  2. Run [bold]owloop run[/]")
    console.print()


STOPPED_REASON_EXIT_1 = {"preflight_failed", "dirty_workspace_declined"}


def _run_engine(
    mode: str, max_iterations: int, worktree: bool, model: str, agent: str,
    idle_timeout: float = 3600, max_duration: int = 0, max_tokens: int = 0,
    ascii: bool = False, no_color: bool = False, compact: bool = False,
) -> None:
    config = EngineConfig(
        project_dir=Path.cwd(),
        mode=mode,
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
        console.print(
            f"[{_brand.AMBER}]Starting autonomous loop...[/]"
            if mode == "build"
            else f"[{_brand.AMBER}]Planning mode — analyzing specs...[/]"
        )
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
    """Shared options for run and plan commands."""
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
        "--max-tokens", type=int, default=0,
        help="Stop loop after N total tokens (0 = unlimited).", show_default=True,
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
    ascii, no_color, compact = _cli_options()
    specs_dir = Path.cwd() / "specs"
    if not specs_dir.exists() or not list(specs_dir.glob("*.md")):
        console = Console(no_color=no_color)
        console.print("[red]Error:[/] No specs found. Create specs in [bold]specs/[/] first.")
        console.print("[dim]Run [bold]owloop init[/] to get started.[/]")
        raise SystemExit(1)

    _run_engine(
        "build", max_iterations, worktree, model, agent,
        idle_timeout, max_duration, max_tokens,
        ascii=ascii, no_color=no_color, compact=compact,
    )


@main.command()
@click.option(
    "--max-iterations", "-n", type=int, default=1,
    help="Maximum planning iterations.", show_default=True,
)
@_common_run_options
def plan(max_iterations: int, worktree: bool, model: str, agent: str,
         idle_timeout: float, max_duration: int, max_tokens: int) -> None:
    """Generate an implementation plan from specs."""
    ascii, no_color, compact = _cli_options()
    _run_engine(
        "plan", max_iterations, worktree, model, agent,
        idle_timeout, max_duration, max_tokens,
        ascii=ascii, no_color=no_color, compact=compact,
    )


@main.command()
def status() -> None:
    """Show current specs and their completion status."""
    ascii, no_color, _compact = _cli_options()
    console = Console(no_color=no_color)
    specs_dir = Path.cwd() / "specs"

    if not specs_dir.exists():
        console.print("[dim]No specs/ directory. Run [bold]owloop init[/] first.[/]")
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
    ascii, no_color, _compact = _cli_options()
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
    ascii, no_color, _compact = _cli_options()
    console = Console(no_color=no_color)
    specs_dir = Path.cwd() / "specs"

    if not specs_dir.is_dir():
        console.print()
        console.print(_banner_text(ascii=ascii, no_color=no_color))
        console.print("[dim]No specs/ directory. Run [bold]owloop init[/] first.[/]")
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
    help="Output path for the HTML report (default: logs/owloop_report.html).",
)
def report(output: Path | None) -> None:
    """Generate an HTML summary report for the latest owloop run."""
    ascii, no_color, _compact = _cli_options()
    console = Console(no_color=no_color)
    generator = ReportGenerator(Path.cwd())
    try:
        report_path = generator.generate(output)
    except FileNotFoundError:
        console.print("[red]Error:[/] No run summary found. Run [bold]owloop run[/] first.")
        raise SystemExit(1) from None
    console.print()
    console.print(_banner_text(ascii=ascii, no_color=no_color))
    console.print(f"[{_brand.GREEN}]✓ Report generated:[/] {report_path}")
    console.print()


if __name__ == "__main__":
    main()
