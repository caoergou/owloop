"""Implementation of the ``owloop go`` command."""

import os
from pathlib import Path

from rich.console import Console
from rich.table import Table

from owloop import _brand
from owloop.adapters import get_adapter
from owloop.cli_config import _load_and_apply_run_config
from owloop.cli_display import (
    AgentStreamDisplay,
    _banner_text,
    _ensure_init,
    _format_spec_table,
)
from owloop.cli_options import DEFAULT_MODEL, _cli_options
from owloop.commands.run import _run_engine
from owloop.spec_generator import SpecGenerationError, SpecGenerator


def go_cmd(
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
