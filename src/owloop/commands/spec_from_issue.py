"""Implementation of the ``owloop spec-from-issue`` command."""

import subprocess
import sys
from pathlib import Path

from rich.console import Console

from owloop import _brand
from owloop.cli_display import _ensure_init
from owloop.cli_options import _cli_options
from owloop.spec_from_issue import IssueToSpecConverter


def spec_from_issue_cmd(
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
