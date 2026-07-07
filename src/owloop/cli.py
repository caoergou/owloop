"""owloop CLI — thin entry point that wires command functions to the click group."""

from pathlib import Path

import click
from rich.console import Console

from owloop import _brand
from owloop.cli_display import _banner_text
from owloop.cli_options import (
    DEFAULT_MODEL,
    MaxTokensParamType,
    _agent_run_options,
    _common_run_options,
    _extra_run_options,
    parse_max_tokens,
)
from owloop.commands.agents import agents_cmd
from owloop.commands.check import check_cmd
from owloop.commands.discover import discover_cmd
from owloop.commands.finish import finish_cmd
from owloop.commands.go import go_cmd
from owloop.commands.init import init_cmd
from owloop.commands.logs import logs_cmd
from owloop.commands.report import report_cmd
from owloop.commands.run import _print_dry_run_report, _run_engine, run_cmd
from owloop.commands.spec import spec_cmd
from owloop.commands.spec_from_issue import spec_from_issue_cmd
from owloop.commands.status import status_cmd
from owloop.commands.version import version_cmd
from owloop.sessions import classify_spec

# Re-export public names used by tests.
__all__ = [
    "main",
    "classify_spec",
    "parse_max_tokens",
    "_run_engine",
    "_print_dry_run_report",
]


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
    """One command: init → generate spec(s) → review → start the loop."""
    go_cmd(
        goal=goal,
        agent=agent,
        model=model,
        verifier_model=verifier_model,
        subagents=subagents,
        idle_timeout=idle_timeout,
        max_duration=max_duration,
        max_tokens=max_tokens,
        worktree=worktree,
        max_iterations=max_iterations,
        resume=resume,
        dry_run=dry_run,
        no_tui=no_tui,
        max_tokens_per_iteration=max_tokens_per_iteration,
        max_turns_per_iteration=max_turns_per_iteration,
        max_budget_usd=max_budget_usd,
        keep_retrying=keep_retrying,
        rollback=rollback,
        notify_webhook=notify_webhook,
        notify_desktop=notify_desktop,
        converge_sweeps=converge_sweeps,
        workers=workers,
        verbose=verbose,
    )


@main.command()
@click.option(
    "--example/--no-example",
    default=True,
    help="Create an example spec file.",
    show_default=True,
)
def init(example: bool) -> None:
    """Initialize owloop in the current project."""
    init_cmd(example=example)


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
    """Turn a vague goal into a concrete spec via agent clarification."""
    spec_cmd(
        goal=goal,
        model=model,
        max_rounds=max_rounds,
        yes=yes,
        agent=agent,
        verifier_model=verifier_model,
        subagents=subagents,
        idle_timeout=idle_timeout,
        max_duration=max_duration,
        max_tokens=max_tokens,
        worktree=worktree,
        max_iterations=max_iterations,
        resume=resume,
        dry_run=dry_run,
        no_tui=no_tui,
        max_tokens_per_iteration=max_tokens_per_iteration,
        max_turns_per_iteration=max_turns_per_iteration,
        max_budget_usd=max_budget_usd,
        keep_retrying=keep_retrying,
        rollback=rollback,
        notify_webhook=notify_webhook,
        notify_desktop=notify_desktop,
        converge_sweeps=converge_sweeps,
        workers=workers,
        verbose=verbose,
    )


@main.command()
def agents() -> None:
    """List available coding-agent presets and whether they're ready to use."""
    agents_cmd()


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
    run_cmd(
        max_iterations=max_iterations,
        resume=resume,
        dry_run=dry_run,
        no_tui=no_tui,
        max_tokens_per_iteration=max_tokens_per_iteration,
        max_turns_per_iteration=max_turns_per_iteration,
        max_budget_usd=max_budget_usd,
        keep_retrying=keep_retrying,
        rollback=rollback,
        notify_webhook=notify_webhook,
        notify_desktop=notify_desktop,
        converge_sweeps=converge_sweeps,
        workers=workers,
        worktree=worktree,
        model=model,
        agent=agent,
        verifier_model=verifier_model,
        subagents=subagents,
        idle_timeout=idle_timeout,
        max_duration=max_duration,
        max_tokens=max_tokens,
    )


@main.command()
def status() -> None:
    """Show current specs and their completion status."""
    status_cmd()


@main.command()
@click.option(
    "--auto",
    is_flag=True,
    default=False,
    help="Automatically merge, push, and clean up the owloop session.",
)
def finish(auto: bool) -> None:
    """Show the latest owloop session and optionally merge/push/cleanup."""
    finish_cmd(auto=auto)


@main.command()
@click.option("--iter", "iter_n", type=int, default=None, help="Show the log for iteration N.")
@click.option("--events", is_flag=True, default=False, help="Show the last 50 events from events.jsonl.")
@click.option("--patch", is_flag=True, default=False, help="Show the latest discarded patch.")
def logs(iter_n: int | None, events: bool, patch: bool) -> None:
    """Inspect owloop log files."""
    logs_cmd(iter_n=iter_n, events=events, patch=patch)


@main.command()
def version() -> None:
    """Show the owloop version."""
    version_cmd()


@main.command()
def discover() -> None:
    """Discover and save project verification commands."""
    discover_cmd()


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
    check_cmd(strict=strict, run_baseline=run_baseline, review=review)


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
    """Generate an HTML summary report for the latest owloop run."""
    report_cmd(output=output, ai=ai, open_report=open_report, model=model)


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
    spec_from_issue_cmd(issue=issue, repo=repo, output=output, dry_run=dry_run)


if __name__ == "__main__":
    main()
