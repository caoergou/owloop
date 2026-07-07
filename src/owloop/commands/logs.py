"""Implementation of the ``owloop logs`` command."""

import json
from pathlib import Path

from rich.console import Console

from owloop.cli_options import _cli_options
from owloop.paths import resolve_logs_dir


def logs_cmd(iter_n: int | None, events: bool, patch: bool) -> None:
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
