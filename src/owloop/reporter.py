"""Plain-text engine event reporter for non-interactive terminals (pipes, CI, logs)."""

from __future__ import annotations

from rich.console import Console

from owloop.engine import RunSummary


class ConsoleReporter:
    """Prints engine events as plain scrolling lines — no full-screen redraw."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def on_event(self, kind: str, data: dict) -> None:
        c = self.console

        if kind == "session_info":
            c.print()
            c.print(f"[bold #d4a025]模式:[/]     {data['mode']}")
            c.print(f"[bold #d4a025]模型:[/]     {data['model']}")
            c.print(f"[bold #d4a025]分支:[/]     {data['branch']}")
            c.print(f"[bold #d4a025]目录:[/]     {data['cwd']}")
            if data["max_iterations"]:
                c.print(f"[bold #d4a025]最大迭代:[/] {data['max_iterations']} 次")
            if data["has_plan"]:
                c.print("[green]✓[/] IMPLEMENTATION_PLAN.md（将使用该文件）")
            elif data["has_specs"]:
                c.print(f"[green]✓[/] specs/（共 {data['spec_count']} 个，{data['incomplete_count']} 个未完成）")
                if data["first_incomplete"]:
                    c.print(f"    下一个未完成: {data['first_incomplete']}")
            else:
                c.print("[red]✗[/] specs/ 目录（未找到 .md 文件）")
            c.print()
        elif kind == "worktree_already_active":
            c.print(f"[cyan]✓ 已在独立 worktree 中运行: {data['path']}[/]")
        elif kind == "worktree_skipped":
            c.print("[cyan]○ 未使用 worktree 隔离，直接在当前目录运行[/]")
        elif kind == "worktree_prompt":
            c.print("[yellow]建议在独立 worktree 中运行以保护主仓库。是否自动创建？(Y/n)[/]")
        elif kind in ("worktree_created", "worktree_branch_reused"):
            c.print(f"[green]✓ 已创建并切换到 worktree: {data['path']}[/]")
        elif kind == "worktree_reused":
            c.print(f"[cyan]目录已存在，直接进入: {data['path']}[/]")
        elif kind == "worktree_declined":
            c.print("[yellow]继续在当前目录运行（未使用 worktree）[/]")
        elif kind == "worktree_failed":
            c.print("[red]✗ 创建 worktree 失败，继续在当前目录运行[/]")
        elif kind == "all_specs_complete":
            c.print(f"[green]全部 {data['spec_count']} 个 spec 均已完成，无事可做。[/]")
        elif kind == "iteration_start":
            c.print()
            c.print(f"[bold purple]════════ 第 {data['iteration']} 轮 ════════[/]")
            c.print(f"[blue][{data['timestamp']}][/] 开始第 {data['iteration']} 轮迭代")
        elif kind == "output_line":
            c.print(data["line"], highlight=False, soft_wrap=True)
        elif kind == "done_signal":
            c.print(f"[green]✓ 检测到完成信号: {data['signal']}[/]")
            c.print("[green]✓ 任务成功完成！[/]")
        elif kind == "no_done_signal":
            c.print("[yellow]⚠ 未检测到完成信号，将在下一轮重试...[/]")
        elif kind == "claude_failed":
            c.print(f"[red]✗ Claude 执行失败（returncode={data['returncode']}）[/]")
        elif kind in ("claude_not_found", "claude_cli_missing"):
            c.print(f"[red]错误: 未找到 Claude CLI ({data['cmd']})[/]")
        elif kind == "stuck_warning":
            c.print(f"[red]⚠ 已连续 {data['consecutive_failures']} 轮未完成，Agent 可能卡住了[/]")
        elif kind == "push_retry":
            c.print(f"[yellow]推送失败，创建远程分支 {data['branch']}...[/]")
        elif kind == "plan_complete":
            c.print()
            c.print("[green]规划完成！[/]")
            c.print("[cyan]运行 'owloop run' 开始构建。[/]")
        elif kind == "interrupted":
            c.print("\n[dim]owloop 已停止[/]")

    def print_summary(self, summary: RunSummary) -> None:
        c = self.console
        c.print()
        c.print("[bold green]═══ OWLOOP 完成 ═══[/]")
        c.print(f"[blue]分支:[/] {summary.branch}")
        c.print(f"[blue]迭代:[/] {summary.iterations} 次")
        if summary.cwd != summary.main_repo_dir:
            c.print(f"[blue]Worktree:[/] {summary.cwd}")
            c.print(f"[cyan]审查:[/] git log --oneline HEAD~{summary.iterations}..HEAD")
            c.print(f"[cyan]合并:[/] cd {summary.main_repo_dir} && git merge {summary.branch}")
            c.print(f"[cyan]丢弃:[/] git worktree remove {summary.cwd}")
        else:
            c.print("[blue]Worktree:[/] 未使用（本次在主仓库运行）")
        c.print()
