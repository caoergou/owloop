"""owloop CLI — entry point for uvx owloop / owloop commands."""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from owloop.adapters import get_adapter
from owloop.engine import EngineConfig, OwloopEngine
from owloop.reporter import ConsoleReporter
from owloop.tui import OwloopTUI

console = Console()

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

OWLOOP_BANNER = Text.from_markup(
    "[bold #d4a025]  ▄▄████▄▄\n"
    " ██ ◉  ◉ ██   owloop\n"
    "███ ╰▽╯ ███[/]\n"
)


def find_script() -> Path | None:
    candidates = [
        Path(__file__).parent.parent.parent / "scripts" / "owloop.sh",
        Path.cwd() / "scripts" / "owloop.sh",
        Path.home() / ".claude" / "skills" / "owloop" / "scripts" / "owloop.sh",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


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


def render_progress_bar(done: int, total: int, width: int = 20) -> str:
    filled = round(width * done / total) if total else 0
    filled = max(0, min(width, filled))
    pct = round(done / total * 100) if total else 0
    return f"[#d4a025]{'█' * filled}[/][dim]{'░' * (width - filled)}[/] {pct}%"


@click.group(invoke_without_command=True)
@click.version_option(package_name="owloop")
@click.pass_context
def main(ctx: click.Context) -> None:
    """🦉 owloop — Your code evolves while you sleep."""
    if ctx.invoked_subcommand is None:
        console.print(OWLOOP_BANNER)
        console.print(
            "[dim]Spec-driven autonomous coding loop for Claude Code.[/]\n"
        )
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
        existing = gitignore.read_text()
        to_add = [e for e in gitignore_entries if e not in existing]
        if to_add:
            with open(gitignore, "a") as f:
                f.write("\n# owloop\n")
                for entry in to_add:
                    f.write(f"{entry}\n")
            created.append(".gitignore (updated)")
    else:
        gitignore.write_text("# owloop\n" + "\n".join(gitignore_entries) + "\n")
        created.append(".gitignore")

    if example:
        example_spec = specs_path / "01-example.md"
        if not example_spec.exists():
            example_spec.write_text(
                SPEC_TEMPLATE.format(name="example-task", priority=1)
            )
            created.append(f"{specs_dir}/01-example.md")

    script = find_script()
    if script:
        target = cwd / "scripts" / "owloop.sh"
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(script, target)
            target.chmod(0o755)
            created.append("scripts/owloop.sh")

        lib_src = script.parent / "lib"
        if lib_src.exists():
            lib_target = target.parent / "lib"
            if not lib_target.exists():
                shutil.copytree(lib_src, lib_target)
                created.append("scripts/lib/")

    console.print()
    console.print(OWLOOP_BANNER)

    if created:
        console.print(
            Panel(
                "\n".join(f"  [green]✓[/] {f}" for f in created),
                title="[bold]Initialized[/]",
                border_style="#d4a025",
                padding=(1, 2),
            )
        )
    else:
        console.print("[dim]Already initialized — nothing to create.[/]")

    console.print()
    console.print("[bold #d4a025]Next steps:[/]")
    console.print(f"  1. Edit [bold]{specs_dir}/01-example.md[/] with your task")
    console.print("  2. Run [bold]owloop run[/]")
    console.print()


def _run_legacy_script(mode: str, max_iterations: int, worktree: bool) -> None:
    script = find_script()
    if not script:
        console.print("[red]Error:[/] owloop.sh not found. Run [bold]owloop init[/] first.")
        raise SystemExit(1)

    env = os.environ.copy()
    if not worktree:
        env["OWLOOP_SKIP_WORKTREE"] = "1"

    cmd = ["bash", str(script)]
    if mode == "plan":
        cmd.append("plan")
    if max_iterations > 0:
        cmd.append(str(max_iterations))

    try:
        result = subprocess.run(cmd, env=env)
        raise SystemExit(result.returncode)
    except KeyboardInterrupt:
        console.print("\n[dim]owloop stopped.[/]")
        raise SystemExit(0)


STOPPED_REASON_EXIT_1 = {"preflight_failed", "dirty_workspace_declined"}


def _run_engine(mode: str, max_iterations: int, worktree: bool, model: str, agent: str) -> None:
    config = EngineConfig(
        project_dir=Path.cwd(),
        mode=mode,
        max_iterations=max_iterations,
        worktree=worktree,
    )
    adapter = get_adapter(
        agent,
        model=model,
        claude_cmd=os.environ.get("CLAUDE_CMD", "claude"),
    )

    if sys.stdout.isatty():
        tui = OwloopTUI()
        try:
            with tui:
                engine = OwloopEngine(config, adapter, on_event=tui.on_event)
                summary = engine.run()
        except KeyboardInterrupt:
            console.print("\n[dim]owloop stopped.[/]")
            raise SystemExit(0)
        tui.print_exit_summary(summary)
    else:
        console.print()
        console.print(OWLOOP_BANNER)
        console.print("[#d4a025]Starting autonomous loop...[/]" if mode == "build" else "[#d4a025]Planning mode — analyzing specs...[/]")
        reporter = ConsoleReporter(console)
        engine = OwloopEngine(config, adapter, on_event=reporter.on_event)
        try:
            summary = engine.run()
        except KeyboardInterrupt:
            console.print("\n[dim]owloop stopped.[/]")
            raise SystemExit(0)
        reporter.print_summary(summary)

    if summary.stopped_reason in STOPPED_REASON_EXIT_1:
        raise SystemExit(1)


@main.command()
@click.option(
    "--max-iterations", "-n",
    type=int,
    default=0,
    help="Maximum iterations (0 = unlimited).",
    show_default=True,
)
@click.option(
    "--worktree/--no-worktree",
    default=True,
    help="Run in an isolated git worktree.",
    show_default=True,
)
@click.option(
    "--model",
    default=DEFAULT_MODEL,
    help="Claude model to use (or set CLAUDE_MODEL).",
    show_default=True,
)
@click.option(
    "--agent",
    type=click.Choice(["claude"]),
    default="claude",
    help="Coding agent adapter to drive the loop with.",
    show_default=True,
)
@click.option(
    "--legacy",
    is_flag=True,
    default=False,
    help="Use the legacy bash loop engine (scripts/owloop.sh) instead of the built-in Python engine.",
)
def run(max_iterations: int, worktree: bool, model: str, agent: str, legacy: bool) -> None:
    """Start the autonomous coding loop."""
    specs_dir = Path.cwd() / "specs"
    if not specs_dir.exists() or not list(specs_dir.glob("*.md")):
        console.print("[red]Error:[/] No specs found. Create specs in [bold]specs/[/] first.")
        console.print("[dim]Run [bold]owloop init[/] to get started.[/]")
        raise SystemExit(1)

    if legacy:
        console.print()
        console.print(OWLOOP_BANNER)
        console.print("[#d4a025]Starting autonomous loop (legacy bash engine)...[/]")
        console.print()
        _run_legacy_script("build", max_iterations, worktree)
        return

    _run_engine("build", max_iterations, worktree, model, agent)


@main.command()
@click.option(
    "--max-iterations", "-n",
    type=int,
    default=1,
    help="Maximum planning iterations.",
    show_default=True,
)
@click.option(
    "--worktree/--no-worktree",
    default=True,
    help="Run in an isolated git worktree.",
    show_default=True,
)
@click.option(
    "--model",
    default=DEFAULT_MODEL,
    help="Claude model to use (or set CLAUDE_MODEL).",
    show_default=True,
)
@click.option(
    "--agent",
    type=click.Choice(["claude"]),
    default="claude",
    help="Coding agent adapter to drive the loop with.",
    show_default=True,
)
@click.option(
    "--legacy",
    is_flag=True,
    default=False,
    help="Use the legacy bash loop engine (scripts/owloop.sh) instead of the built-in Python engine.",
)
def plan(max_iterations: int, worktree: bool, model: str, agent: str, legacy: bool) -> None:
    """Generate an implementation plan from specs."""
    if legacy:
        console.print()
        console.print(OWLOOP_BANNER)
        console.print("[#d4a025]Planning mode — analyzing specs (legacy bash engine)...[/]")
        console.print()
        _run_legacy_script("plan", max_iterations, worktree)
        return

    _run_engine("plan", max_iterations, worktree, model, agent)


@main.command()
def status() -> None:
    """Show current specs and their completion status."""
    specs_dir = Path.cwd() / "specs"

    if not specs_dir.exists():
        console.print("[dim]No specs/ directory. Run [bold]owloop init[/] first.[/]")
        raise SystemExit(1)

    specs = sorted(specs_dir.glob("*.md"))
    if not specs:
        console.print("[dim]No spec files found in specs/.[/]")
        raise SystemExit(0)

    console.print()
    console.print(OWLOOP_BANNER)

    from rich.table import Table

    table = Table(
        title="Specs",
        border_style="#d4a025",
        show_lines=False,
        padding=(0, 2),
    )
    table.add_column("", width=3)
    table.add_column("File", style="bold")
    table.add_column("Priority", justify="center")
    table.add_column("Status", justify="center")

    STATE_DISPLAY = {
        "done": ("[green]✓[/]", "[green]done[/]"),
        "in_progress": ("[#d4a025]🦉[/]", "[#d4a025]in progress[/]"),
        "pending": ("[dim]○[/]", "[dim]pending[/]"),
    }

    counts = {"done": 0, "in_progress": 0, "pending": 0}

    for spec_file in specs:
        content = spec_file.read_text()
        state = classify_spec(content)
        counts[state] += 1

        priority = "—"
        for line in content.splitlines():
            if line.strip().startswith("## Priority:"):
                priority = line.split(":")[-1].strip()
                break

        icon, status_text = STATE_DISPLAY[state]
        table.add_row(icon, spec_file.name, priority, status_text)

    total = len(specs)
    console.print(
        f"  [green]✓ {counts['done']} done[/] · "
        f"[#d4a025]🦉 {counts['in_progress']} in progress[/] · "
        f"[dim]○ {counts['pending']} pending[/]"
    )
    console.print(f"  {render_progress_bar(counts['done'], total)}")
    console.print()
    console.print(table)
    console.print()


@main.command()
def version() -> None:
    """Show the owloop version."""
    from importlib.metadata import PackageNotFoundError, version as pkg_version

    try:
        v = pkg_version("owloop")
    except PackageNotFoundError:
        v = "0.0.0-dev"

    console.print()
    console.print(OWLOOP_BANNER)
    console.print(f"[bold]owloop[/] [#d4a025]v{v}[/]")
    console.print()


if __name__ == "__main__":
    main()
