"""Plain-text engine event reporter for non-interactive terminals (pipes, CI, logs)."""

from __future__ import annotations

from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from owloop import _brand
from owloop.engine import RunSummary


class ConsoleReporter:
    """Prints engine events as plain scrolling lines — no full-screen redraw."""

    def __init__(self, console: Console | None = None, ascii: bool = False) -> None:
        self.console = console or Console()
        self.ascii = ascii

    def _mark(self, kind: str) -> str:
        """Return an event prefix symbol, using ASCII when ``self.ascii`` is set."""
        symbols = {
            "ok": ("✓", "+"),
            "fail": ("✗", "-"),
            "warn": ("⚠", "!"),
            "info": ("○", ">"),
            "clock": ("⏱", "T"),
        }
        return symbols[kind][1 if self.ascii else 0]

    def _status(self, phase: str, iteration: int = 0, spec_name: str = "") -> str:
        """Return a state-aware message, stripping emoji in ASCII mode."""
        msg = _brand.status_message(phase, iteration=iteration, spec_name=spec_name)
        if self.ascii:
            msg = msg.lstrip("🦉✗💤🌙🌅 ")
        return msg

    def on_event(self, kind: str, data: dict) -> None:
        c = self.console

        if kind == "session_info":
            c.print()
            c.print(f"[bold {_brand.AMBER}]Mode:[/]          {data['mode']}")
            c.print(f"[bold {_brand.AMBER}]Model:[/]         {data['model']}")
            c.print(f"[bold {_brand.AMBER}]Branch:[/]        {data['branch']}")
            c.print(f"[bold {_brand.AMBER}]Directory:[/]     {data['cwd']}")
            if data["max_iterations"]:
                c.print(f"[bold {_brand.AMBER}]Max iterations:[/] {data['max_iterations']}")
            if data["has_plan"]:
                c.print(f"[{_brand.GREEN}]{self._mark('ok')} IMPLEMENTATION_PLAN.md (will be used)[/]")
            elif data["has_specs"]:
                c.print(
                    f"[{_brand.GREEN}]{self._mark('ok')} specs/"
                    f" ({data['spec_count']} total, {data['incomplete_count']} incomplete)[/]"
                )
                if data["first_incomplete"]:
                    c.print(f"    next incomplete: {data['first_incomplete']}")
            else:
                c.print(f"[{_brand.RED}]{self._mark('fail')} specs/ directory (no .md files found)[/]")
            c.print()
        elif kind == "worktree_already_active":
            c.print(f"[{_brand.CYAN}]{self._mark('ok')} running in isolated worktree: {data['path']}[/]")
        elif kind == "worktree_skipped":
            c.print(f"[{_brand.CYAN}]{self._mark('info')} worktree isolation disabled, running in current directory[/]")
        elif kind == "worktree_prompt":
            c.print(f"[{_brand.AMBER}]It is recommended to run in an isolated worktree to protect the main repo. Auto-create? (Y/n)[/]")
        elif kind == "worktree_auto_created":
            c.print(f"[{_brand.CYAN}]non-interactive environment, auto-creating isolated worktree to protect the main repo[/]")
        elif kind in ("worktree_created", "worktree_branch_reused"):
            c.print(f"[{_brand.GREEN}]{self._mark('ok')} created and switched to worktree: {data['path']}[/]")
        elif kind == "worktree_reused":
            c.print(f"[{_brand.CYAN}]directory exists, entering: {data['path']}[/]")
        elif kind == "worktree_declined":
            c.print(f"[{_brand.AMBER}]continuing in current directory (worktree isolation disabled)[/]")
        elif kind == "worktree_failed":
            c.print(f"[{_brand.RED}]{self._mark('fail')} failed to create worktree, continuing in current directory[/]")
        elif kind == "all_specs_complete":
            c.print(f"[{_brand.GREEN}]{self._mark('ok')} {self._status('complete')}[/]")
        elif kind == "iteration_start":
            c.print()
            c.print(f"[bold {_brand.CYAN}]════════ {self._status('iteration', iteration=data['iteration'])} ════════[/]")
            c.print(f"[{_brand.CYAN}][{data['timestamp']}][/] starting iteration {data['iteration']}")
        elif kind == "output_line":
            c.print(data["line"], highlight=False, soft_wrap=True)
        elif kind == "done_signal":
            c.print(f"[{_brand.GREEN}]{self._mark('ok')} {self._status('done_signal', iteration=data['iteration'])}[/]")
            c.print(f"[{_brand.GREEN}]{self._mark('ok')} task completed successfully![/]")
        elif kind == "no_done_signal":
            c.print(f"[{_brand.AMBER}]{self._mark('warn')} no done signal detected, will retry in next iteration...[/]")
        elif kind == "agent_failed":
            c.print(f"[{_brand.RED}]{self._mark('fail')} agent failed (returncode={data['returncode']})[/]")
        elif kind == "agent_timeout":
            c.print(f"[{_brand.RED}]{self._mark('clock')} iteration {data['iteration']} idle timeout, agent may be hung, terminated[/]")
        elif kind == "preflight_failed":
            c.print(f"[{_brand.RED}]preflight check failed:[/]")
            for issue in data["issues"]:
                c.print(f"  [{_brand.RED}]{self._mark('fail')} {issue}[/]")
        elif kind == "dirty_workspace_warning":
            c.print(f"[{_brand.AMBER}]{self._mark('warn')} workspace has uncommitted changes, they will not appear in the worktree.[/]")
            c.print(f"[{_brand.AMBER}]   please commit or stash before running {_brand.OLLIE_NAME}.[/]")
            c.print(f"[{_brand.AMBER}]   continue? (y/N)[/]")
        elif kind == "dirty_workspace_declined":
            c.print(f"[{_brand.RED}]cancelled — please commit or stash before running {_brand.OLLIE_NAME}.[/]")
        elif kind == "dirty_workspace_noninteractive_continue":
            c.print(f"[{_brand.CYAN}]non-interactive environment, ignoring uncommitted changes warning, continuing[/]")
        elif kind == "claude_config_copied":
            c.print(f"[{_brand.CYAN}]copied .claude/ config to worktree: {data['path']}[/]")
        elif kind == "stuck_warning":
            c.print(
                f"[{_brand.RED}]{self._mark('warn')} "
                f"{data['consecutive_failures']} consecutive incomplete iterations, {self._status('stuck')}[/]"
            )
        elif kind == "fix_loop_warning":
            files = ", ".join(data["files"][:5])
            c.print(f"[{_brand.AMBER}]{self._mark('warn')} detected fix loop: {files} modified for {data['consecutive']} consecutive iterations[/]")
        elif kind == "max_duration_reached":
            c.print(f"[{_brand.AMBER}]{self._mark('clock')} reached maximum run time ({data['minutes']} minutes), stopping loop[/]")
        elif kind == "push_retry":
            c.print(f"[{_brand.AMBER}]{self._mark('warn')} push failed, creating remote branch {data['branch']}...[/]")
        elif kind == "plan_complete":
            c.print()
            c.print(f"[{_brand.GREEN}]{self._mark('ok')} planning complete![/]")
            c.print(f"[{_brand.CYAN}]run 'owloop run' to start building.[/]")
        elif kind == "interrupted":
            c.print("\n[dim]owloop stopped[/]")

    FAILED_REASONS = {"preflight_failed", "dirty_workspace_declined"}

    def print_summary(self, summary: RunSummary) -> None:
        c = self.console
        failed = summary.stopped_reason in self.FAILED_REASONS

        owl_art = _brand.ASCII_OWL_SMALL if self.ascii else _brand.OWL_SLEEP
        owl = Text("\n".join(owl_art), justify="center")

        facts = Table.grid(padding=(0, 2))
        facts.add_column(style=f"dim {_brand.GRAY}", justify="right")
        facts.add_column(style=_brand.MOON_WHITE)
        facts.add_row("Branch", summary.branch)
        facts.add_row("Iterations", str(summary.iterations))

        hints = _brand.exit_hints(
            branch=summary.branch,
            iterations=summary.iterations,
            cwd=str(summary.cwd),
            main_repo_dir=str(summary.main_repo_dir),
        )

        if failed:
            owl.stylize(f"dim {_brand.RED}")
            body = Group(
                owl,
                Align.center(Text(f"{self._mark('fail')} {_brand.OLLIE_NAME} failed to start", style=f"bold {_brand.RED}")),
                Align.center(Text("\n".join(f"· {issue}" for issue in (summary.issues or [])), style=f"dim {_brand.GRAY}")),
            )
            c.print(Panel(body, border_style=_brand.RED, padding=(1, 4), width=56))
            return

        owl.stylize(f"dim {_brand.AMBER}")
        body = Group(
            owl,
            Align.center(Text(self._status("complete"), style=f"bold {_brand.AMBER}")),
            Align.center(facts),
            Align.center(Text("\n".join(hints), style=f"dim {_brand.GRAY}")),
        )
        c.print(Panel(body, border_style=_brand.AMBER, padding=(1, 4), width=56))
