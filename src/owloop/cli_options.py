"""Shared Click options and parameter types for the owloop CLI."""

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import click

from owloop.adapters import DEFAULT_IDLE_TIMEOUT

DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")

MAX_TOKENS_UNITS = {
    "k": 1_000,
    "w": 10_000,
    "m": 1_000_000,
}


def parse_max_tokens(value: str) -> int:
    """Parse a token limit, supporting shorthand like 10k, 1w, 2m.

    Args:
        value: Raw user input. Plain integers pass through; suffixes
            ``k`` (thousand), ``w`` (ten-thousand), and ``m`` (million)
            are expanded.

    Returns:
        Token count as an integer.

    Raises:
        click.BadParameter: if the value cannot be parsed.
    """
    value = value.strip().lower()
    if not value:
        raise click.BadParameter("token limit cannot be empty")

    if value.isdigit():
        return int(value)

    suffix = value[-1]
    if suffix not in MAX_TOKENS_UNITS:
        raise click.BadParameter(
            f"invalid token limit: {value!r}. Use a number or add k/w/m (e.g. 10k, 1w, 2m)"
        )

    number_part = value[:-1]
    if not number_part or not number_part.replace(".", "", 1).isdigit():
        raise click.BadParameter(
            f"invalid token limit: {value!r}. Use a number or add k/w/m (e.g. 10k, 1w, 2m)"
        )

    number = float(number_part)
    return int(number * MAX_TOKENS_UNITS[suffix])


class MaxTokensParamType(click.ParamType):
    """Click parameter type that parses token limit shorthand."""

    name = "tokens"

    def convert(self, value: object, param: click.Parameter | None, ctx: click.Context | None) -> int:
        if isinstance(value, int):
            return value
        return parse_max_tokens(str(value))


def _cli_options() -> tuple[bool, bool, bool, bool]:
    """Read global --ascii / --no-color / --compact / --verbose flags from the current Click context."""
    ctx = click.get_current_context()
    obj = ctx.ensure_object(dict)
    return bool(obj.get("ascii")), bool(obj.get("no_color")), bool(obj.get("compact")), bool(obj.get("verbose"))


def _validate_agent(ctx: click.Context, param: click.Parameter, value: str) -> str:
    """Validate --agent against builtin + user presets (.owloop/agents.toml)."""
    from owloop.presets import all_presets

    keys = sorted(all_presets(Path.cwd()))
    if value not in keys:
        raise click.BadParameter(f"unknown agent {value!r}. Available: {', '.join(keys)}")
    return value


def _agent_run_options(f: Callable[..., Any]) -> Callable[..., Any]:
    """Shared non-model run options for run, go, and spec."""
    f = click.option(
        "--agent", default="claude", metavar="AGENT", callback=_validate_agent,
        help="Coding agent preset (see `owloop agents` for the full list).",
        show_default=True,
    )(f)
    f = click.option(
        "--verifier-model",
        help="Claude model for the independent verifier agent (defaults to --model).",
        default=None,
    )(f)
    f = click.option(
        "--subagents",
        is_flag=True,
        default=False,
        help="Split large iterations into Orient/Implement/Verify subagent phases.",
    )(f)
    f = click.option(
        "--idle-timeout", type=float, default=DEFAULT_IDLE_TIMEOUT,
        help="Kill agent after N seconds without output.", show_default=True,
    )(f)
    f = click.option(
        "--max-duration", type=int, default=0,
        help="Stop loop after N minutes total (0 = unlimited).", show_default=True,
    )(f)
    f = click.option(
        "--max-tokens", type=MaxTokensParamType(), default=0,
        help="Stop loop after N total tokens (0 = unlimited; supports k/w/m shorthand).", show_default=True,
    )(f)
    f = click.option(
        "--worktree/--no-worktree", default=True,
        help="Run in an isolated git worktree.", show_default=True,
    )(f)
    return f


def _common_run_options(f: Callable[..., Any]) -> Callable[..., Any]:
    """Shared options for the run and go commands (includes --model default None)."""
    f = click.option(
        "--model", default=None, metavar="MODEL",
        help="Model to use (defaults per agent; claude honors CLAUDE_MODEL).",
    )(f)
    return _agent_run_options(f)


def _extra_run_options(f: Callable[..., Any]) -> Callable[..., Any]:
    """Additional run options forwarded by run, go, and spec."""
    f = click.option(
        "--max-iterations", "-n", type=int, default=0,
        help="Maximum iterations (0 = unlimited).", show_default=True,
    )(f)
    f = click.option(
        "--resume",
        is_flag=True,
        default=False,
        help="Resume the most recent owloop session (reuse its worktree and branch).",
    )(f)
    f = click.option(
        "--dry-run", "--one-shot", "dry_run",
        is_flag=True,
        default=False,
        help="Run exactly one iteration, print a pass/fail report, and skip push "
        "(no committed changes are left behind). Use to validate specs without "
        "burning a full overnight run.",
    )(f)
    f = click.option(
        "--no-tui", "--plain", "no_tui",
        is_flag=True,
        default=False,
        help="Bypass the full-screen TUI and print plain console output, even in a TTY.",
    )(f)
    f = click.option(
        "--max-tokens-per-iteration", type=MaxTokensParamType(), default=0,
        help="Kill a single iteration early if it exceeds N tokens (0 = unlimited; "
        "supports k/w/m shorthand).", show_default=True,
    )(f)
    f = click.option(
        "--max-turns-per-iteration", type=int, default=0,
        help="Forward --max-turns N to `claude -p` so a single iteration is bounded "
        "at the source (0 = unlimited; ignored on CLIs without the flag).",
        show_default=True,
    )(f)
    f = click.option(
        "--max-budget-usd", type=float, default=0.0,
        help="Forward a per-iteration USD budget cap to the CLI when supported "
        "(0 = unlimited).", show_default=True,
    )(f)
    f = click.option(
        "--keep-retrying", is_flag=True, default=False,
        help="Legacy behavior: warn and back off on repeated failures instead of "
        "hard-stopping with a `stalled` terminal state.",
    )(f)
    f = click.option(
        "--rollback/--no-rollback", default=True, show_default=True,
        help="Reset the worktree to the last good commit after a failed iteration "
        "(a discarded-diff patch is saved under .owloop/logs/).",
    )(f)
    f = click.option(
        "--notify-webhook", default=None, metavar="URL",
        help="POST a JSON completion notification to this webhook when the run stops "
        "on an attention-worthy state (or set OWLOOP_NOTIFY_WEBHOOK).",
    )(f)
    f = click.option(
        "--notify-desktop", is_flag=True, default=False,
        help="Fire a native desktop notification when the run stops.",
    )(f)
    f = click.option(
        "--converge", "converge_sweeps", type=int, default=0, metavar="N",
        help="After the spec queue empties, run up to N audit sweeps that append gap "
        "specs until the codebase converges on the goal (0 = disabled).",
        show_default=True,
    )(f)
    f = click.option(
        "--workers", type=int, default=1, metavar="N",
        help="Run up to N file-disjoint specs concurrently, each in its own worktree "
        "(1 = sequential). Specs need a `## Files` scope to be scheduled in parallel.",
        show_default=True,
    )(f)
    return f
