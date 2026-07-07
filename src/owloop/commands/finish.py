"""Implementation of the ``owloop finish`` command."""

import shutil
import subprocess
from pathlib import Path

from rich.console import Console
from rich.table import Table

from owloop import _brand, git_stats
from owloop.cli_config import _default_report_path
from owloop.cli_display import _banner_text
from owloop.cli_options import _cli_options
from owloop.sessions import _find_worktree_path, _read_latest_session


def finish_cmd(auto: bool) -> None:
    """Show the latest owloop session and optionally merge/push/cleanup."""
    ascii, no_color, _compact, _verbose = _cli_options()
    console = Console(no_color=no_color)
    project_dir = Path.cwd()

    session = _read_latest_session(project_dir)
    if not session:
        console.print("[red]Error:[/] No latest session found. Run [bold]owloop run[/] first.")
        raise SystemExit(1)

    session_id = session.get("session_id", "—")
    branch = session.get("branch", "—")
    wt_path = _find_worktree_path(project_dir, session)
    stopped_reason = session.get("stopped_reason", session.get("status", "—"))
    iterations = session.get("iterations", 0)

    console.print()
    console.print(_banner_text(ascii=ascii, no_color=no_color))

    table = Table(
        title="Latest owloop session",
        border_style=_brand.AMBER,
        show_lines=False,
        padding=(0, 2),
    )
    table.add_column("Key", style="bold")
    table.add_column("Value")
    table.add_row("Session", str(session_id))
    table.add_row("Branch", str(branch))
    table.add_row("Worktree", str(wt_path) if wt_path else "—")
    table.add_row("Stopped reason", str(stopped_reason))
    table.add_row("Iterations", str(iterations))
    console.print(table)
    console.print()

    # Diff summary
    cwd = wt_path if wt_path and wt_path.is_dir() and branch.startswith("owloop/") else project_dir
    commits = git_stats.get_recent_commits(cwd, iterations)
    total_files, total_ins, total_del = git_stats.total_diff_stats(commits)
    console.print(
        f"Diff: {total_files} files · [green]+{total_ins}[/] · [red]-{total_del}[/]"
    )
    for commit in commits:
        console.print(f"  [cyan]{commit.hash}[/] {commit.message}")
    console.print()

    report_path = _default_report_path()
    if report_path.exists():
        console.print(f"Report: {report_path}")
    else:
        console.print("Report: not generated")
    console.print()

    # Base branch detection
    base_branch = "main"
    for candidate in ("main", "master"):
        result = subprocess.run(
            ["git", "show-ref", "--verify", f"refs/heads/{candidate}"],
            cwd=project_dir,
            capture_output=True,
        )
        if result.returncode == 0:
            base_branch = candidate
            break

    console.print(f"[{_brand.AMBER}]Next steps:[/]")
    console.print(f"  review:  git -C {project_dir} log --oneline {base_branch}..{branch}")
    console.print(f"  merge:   git -C {project_dir} checkout {base_branch} && git merge {branch}")
    console.print(f"  push:    git -C {project_dir} push origin {base_branch}")
    if wt_path:
        console.print(f"  cleanup: git -C {project_dir} worktree remove {wt_path} && git -C {project_dir} branch -d {branch}")
    console.print("  resume:  owloop run --resume")
    console.print()

    if not auto:
        return

    # Auto mode: merge, push, remove worktree, delete branch. Stop on first failure.
    console.print(f"[{_brand.AMBER}]Auto-finishing session...[/]")

    def _git_step(desc: str, cwd: Path, *args: str) -> bool:
        console.print(f"  {desc} ...", end=" ")
        result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
        if result.returncode != 0:
            console.print(f"[red]failed[/]\n{result.stderr.strip()}")
            return False
        console.print(f"[{_brand.GREEN}]ok[/]")
        return True

    # Idempotent merge: skip if already merged.
    merge_check = subprocess.run(
        ["git", "merge-base", "--is-ancestor", branch, base_branch],
        cwd=project_dir,
        capture_output=True,
    )
    already_merged = merge_check.returncode == 0

    if not already_merged:
        if not _git_step(f"checkout {base_branch}", project_dir, "checkout", base_branch):
            raise SystemExit(1)
        if not _git_step(f"merge {branch}", project_dir, "merge", "--no-ff", branch, "-m", f"owloop: merge {branch}"):
            raise SystemExit(1)
    else:
        console.print(f"  [dim]{branch} already merged into {base_branch}[/]")

    if not _git_step("push", project_dir, "push", "origin", base_branch):
        raise SystemExit(1)

    if wt_path and wt_path.exists():
        # Remove worktree if it exists.
        subprocess.run(["git", "worktree", "remove", "--force", str(wt_path)], cwd=project_dir, capture_output=True)
        if wt_path.exists():
            shutil.rmtree(wt_path, ignore_errors=True)

    # Delete branch if it still exists.
    branch_exists = subprocess.run(
        ["git", "show-ref", "--verify", f"refs/heads/{branch.split('/', 1)[1]}"],
        cwd=project_dir,
        capture_output=True,
    ).returncode == 0
    if branch_exists:
        short_branch = branch.split("/", 1)[1]
        if not _git_step(f"delete branch {short_branch}", project_dir, "branch", "-d", short_branch):
            raise SystemExit(1)

    console.print(f"[{_brand.GREEN}]✓ Session finished.[/]")
    console.print()
