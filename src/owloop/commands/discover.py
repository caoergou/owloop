"""Implementation of the ``owloop discover`` command."""

from pathlib import Path

from rich.console import Console

from owloop import _brand
from owloop.backpressure import discover_and_save
from owloop.cli_display import _banner_text
from owloop.cli_options import _cli_options


def discover_cmd() -> None:
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
