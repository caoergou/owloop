"""Implementation of the ``owloop agents`` command."""

import os
import shutil as _shutil
from pathlib import Path

from rich.console import Console
from rich.table import Table

from owloop import _brand
from owloop.cli_options import _cli_options
from owloop.presets import all_presets


def agents_cmd() -> None:
    """List available coding-agent presets and whether they're ready to use.

    Two integration paths exist: native adapters (claude, kimi) and ACP —
    the Agent Client Protocol (https://agentclientprotocol.com) — which
    covers every other preset with a single implementation. Add your own
    ACP agents in ``.owloop/agents.toml``.
    """
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
