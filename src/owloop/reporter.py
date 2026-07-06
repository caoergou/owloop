"""Plain-text engine event reporter for non-interactive terminals (pipes, CI, logs)."""

from __future__ import annotations

from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from owloop import _brand
from owloop.engine import RunSummary, TerminalState
from owloop.git_stats import get_recent_commits, total_diff_stats


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
            c.print(f"[bold {_brand.AMBER}]Model:[/]         {data['model']}")
            c.print(f"[bold {_brand.AMBER}]Branch:[/]        {data['branch']}")
            c.print(f"[bold {_brand.AMBER}]Directory:[/]     {data['cwd']}")
            if data["max_iterations"]:
                c.print(f"[bold {_brand.AMBER}]Max iterations:[/] {data['max_iterations']}")
            if data["has_specs"]:
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
        elif kind == "blocked":
            c.print(f"[{_brand.RED}]{self._mark('fail')} blocked: {data['payload']}[/]")
        elif kind == "decide":
            c.print(f"[{_brand.AMBER}]{self._mark('warn')} decision needed: {data['payload']}[/]")
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
        elif kind == "stalled":
            c.print(
                f"[{_brand.RED}]{self._mark('fail')} stalled: {data.get('failures')} × "
                f"{data.get('reason')} ({data.get('failure_reason', '')}) — stopping[/]"
            )
        elif kind == "spec_tampered":
            c.print(
                f"[{_brand.RED}]{self._mark('fail')} spec tampering detected "
                f"(acceptance criteria / backpressure changed mid-iteration) — iteration failed[/]"
            )
        elif kind == "verification_gate_passed":
            c.print(f"[{_brand.GREEN}]{self._mark('ok')} verification gate passed ({data.get('passed', 0)} checks)[/]")
        elif kind == "verification_gate_failed":
            c.print(
                f"[{_brand.RED}]{self._mark('fail')} verification gate failed "
                f"({data.get('failed', 0)} of {data.get('passed', 0) + data.get('failed', 0)} checks)[/]"
            )
        elif kind == "iteration_rolled_back":
            c.print(f"[{_brand.CYAN}]{self._mark('info')} rolled back to {data.get('to_commit')} (failed iteration discarded)[/]")
        elif kind == "iteration_exhausted":
            c.print(f"[{_brand.AMBER}]{self._mark('clock')} iteration hit its native turn/token limit[/]")
        elif kind == "fix_loop_warning":
            files = ", ".join(data["files"][:5])
            c.print(f"[{_brand.AMBER}]{self._mark('warn')} detected fix loop: {files} modified for {data['consecutive']} consecutive iterations[/]")
        elif kind == "max_duration_reached":
            c.print(f"[{_brand.AMBER}]{self._mark('clock')} reached maximum run time ({data['minutes']} minutes), stopping loop[/]")
        elif kind == "tokens_update":
            c.print(f"[{_brand.CYAN}]{self._mark('info')} tokens: +{data['tokens_used']:,} this round · {data['total_tokens']:,} total[/]")
        elif kind == "max_tokens_reached":
            c.print(f"[{_brand.AMBER}]{self._mark('clock')} token budget reached ({data['tokens']:,} / {data['limit']:,}), stopping loop[/]")
        elif kind == "push_retry":
            c.print(f"[{_brand.AMBER}]{self._mark('warn')} push failed, creating remote branch {data['branch']}...[/]")
        elif kind == "interrupted":
            c.print("\n[dim]owloop stopped[/]")

    FAILED_REASONS = {"preflight_failed", "dirty_workspace_declined"}

    def _gather_summary_stats(self, summary: RunSummary) -> tuple[list, tuple[int, int, int]]:
        """Fetch recent commits and total diff stats from ``summary.cwd``."""
        commits = get_recent_commits(summary.cwd, summary.iterations)
        total_files, total_ins, total_del = total_diff_stats(commits)
        return commits, (total_files, total_ins, total_del)

    def _commit_lines(self, commits: list) -> list[str]:
        """Format commits as short hash + message lines."""
        if not commits:
            return ["No commits recorded for this run."]
        return [f"{commit.hash}  {commit.message}" for commit in commits]

    def _review_commands(self, iterations: int) -> list[str]:
        return [
            f"git log --oneline HEAD~{iterations}..HEAD",
            f"git diff --stat HEAD~{iterations}..HEAD",
        ]

    def print_summary(self, summary: RunSummary) -> None:
        c = self.console
        failed = summary.stopped_reason in self.FAILED_REASONS

        owl = Text(
            _brand.BRAND_BAR_ASCII if self.ascii else _brand.BRAND_BAR,
            style=f"bold {_brand.AMBER}",
            justify="center",
        )

        commits, (total_files, total_ins, total_del) = self._gather_summary_stats(summary)
        commit_lines = self._commit_lines(commits)
        commands = self._review_commands(summary.iterations)

        facts = Table.grid(padding=(0, 2))
        facts.add_column(style=f"dim {_brand.GRAY}", justify="right")
        facts.add_column(style=_brand.MOON_WHITE)
        facts.add_row("Branch", summary.branch)
        facts.add_row("Iterations", str(summary.iterations))
        facts.add_row("Stopped reason", summary.stopped_reason)
        if summary.blocker:
            facts.add_row("Blocker", summary.blocker)
        if summary.decision_question:
            facts.add_row("Decision", summary.decision_question)
        facts.add_row("Diff", f"{total_files} files · [green]+{total_ins}[/] · [red]-{total_del}[/]")
        if summary.tokens_used:
            facts.add_row("Tokens", f"{summary.tokens_used:,}")

        commits_table = Table.grid(padding=(0, 2))
        commits_table.add_column(style=f"bold {_brand.CYAN}")
        commits_table.add_column(style=_brand.MOON_WHITE)
        for line in commit_lines:
            if line.startswith("No commits"):
                commits_table.add_row("", f"[dim]{line}[/dim]")
            else:
                hash_part, _, message = line.partition("  ")
                commits_table.add_row(hash_part, message)

        commands_table = Table.grid(padding=(0, 2))
        commands_table.add_column(style=f"dim {_brand.GRAY}", justify="right")
        commands_table.add_column(style=_brand.MOON_WHITE)
        commands_table.add_row("Review", commands[0])
        for command in commands[1:]:
            commands_table.add_row("", command)

        hints = _brand.exit_hints(
            branch=summary.branch,
            iterations=summary.iterations,
            cwd=str(summary.cwd),
            main_repo_dir=str(summary.main_repo_dir),
        )

        sections: list = [Align.center(facts)]
        if commits:
            sections.append(Align.center(Text("Commits", style=f"bold {_brand.AMBER}")))
            sections.append(Align.center(commits_table))
        sections.append(Align.center(commands_table))
        if hints:
            sections.append(Align.center(Text("\n".join(hints), style=f"dim {_brand.GRAY}")))

        # A run that ran out of budget did not finish its work: never let
        # `exhausted` (or `stalled`) read as a clean success.
        if summary.state == TerminalState.EXHAUSTED:
            sections.append(
                Align.center(
                    Text(
                        f"{self._mark('warn')} Budget exhausted ({summary.stopped_reason}) — "
                        f"work is NOT complete; review costs before the next run",
                        style=f"bold {_brand.RED}",
                    )
                )
            )
        elif summary.state == TerminalState.STALLED:
            sections.append(
                Align.center(
                    Text(
                        f"{self._mark('warn')} Stalled ({summary.stopped_reason}) — "
                        f"no progress; inspect the discarded patches in .owloop/logs/",
                        style=f"bold {_brand.RED}",
                    )
                )
            )

        if failed:
            owl.stylize(f"dim {_brand.RED}")
            body = Group(
                owl,
                Align.center(Text(f"{self._mark('fail')} {_brand.OLLIE_NAME} failed to start", style=f"bold {_brand.RED}")),
                Align.center(Text("\n".join(f"· {issue}" for issue in (summary.issues or [])), style=f"dim {_brand.GRAY}")),
            )
            c.print(Panel(body, border_style=_brand.RED, padding=(1, 4), width=64))
            return

        # Headline honors the terminal state so "complete" is reserved for a
        # genuine success — an exhausted or stalled run gets its own wording.
        incomplete_states = {TerminalState.EXHAUSTED, TerminalState.STALLED}
        if summary.state in incomplete_states:
            headline = Text(f"{self._mark('warn')} owloop stopped without finishing", style=f"bold {_brand.RED}")
            border = _brand.RED
        else:
            headline = Text(self._status("complete"), style=f"bold {_brand.AMBER}")
            border = _brand.AMBER
        owl.stylize(f"dim {_brand.AMBER}")
        body = Group(owl, Align.center(headline), *sections)
        c.print(Panel(body, border_style=border, padding=(1, 4), width=64))
