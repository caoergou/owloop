"""Implementation of the ``owloop run`` command and engine runner helpers."""

import os
import sys
from pathlib import Path
from typing import Any, cast

from rich.console import Console

from owloop import _brand
from owloop.adapters import DEFAULT_IDLE_TIMEOUT, get_adapter
from owloop.cli_config import _generate_quick_report, _load_and_apply_run_config
from owloop.cli_display import _banner_text
from owloop.cli_options import _cli_options
from owloop.engine import EngineConfig, OwloopEngine, RunSummary, TerminalState
from owloop.paths import resolve_specs_dir
from owloop.reporter import ConsoleReporter
from owloop.tui import OwloopTUI

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
    no_tui: bool = False, dry_run: bool = False, no_push: bool = False,
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
        no_push=no_push,
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
    no_push = kwargs["no_push"]
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
        no_push=no_push,
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
    from rich.panel import Panel

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


def run_cmd(
    max_iterations: int, resume: bool, dry_run: bool, no_push: bool, no_tui: bool,
    max_tokens_per_iteration: int, max_turns_per_iteration: int, max_budget_usd: float,
    keep_retrying: bool, rollback: bool, notify_webhook: str | None, notify_desktop: bool,
    converge_sweeps: int, workers: int, worktree: bool, model: str, agent: str,
    verifier_model: str | None, subagents: bool, idle_timeout: float, max_duration: int,
    max_tokens: int,
) -> None:
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
        no_push=no_push,
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
