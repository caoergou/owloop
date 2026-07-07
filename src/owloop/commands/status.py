"""Implementation of the ``owloop status`` command."""

from pathlib import Path

from rich.console import Console
from rich.table import Table

from owloop import _brand
from owloop.cli_display import _banner_text, render_progress_bar
from owloop.cli_options import _cli_options
from owloop.paths import resolve_specs_dir
from owloop.sessions import _find_worktree_path, _read_latest_session, classify_spec


def status_cmd() -> None:
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
