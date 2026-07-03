"""Python port of scripts/owloop.sh — the autonomous build/plan loop engine.

The engine spawns one fresh agent iteration (via an `AgentAdapter`) per round,
watches its output for the ``<promise>DONE</promise>`` completion signal,
commits/pushes on success, and retries (up to a consecutive-failure limit)
otherwise.

All UI concerns (TUI, plain console) live outside this module: the engine
only reports progress through the ``on_event(kind, data)`` callback so it can
be driven headless (tests, CI) or rendered any way the caller likes. Talking
to the underlying coding agent goes through `AgentAdapter` (see adapters.py)
so the engine itself never shells out to `claude` directly.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from owloop import spec_queue
from owloop.adapters import AgentAdapter

BUILD_PROMPT = """\
# Owloop — Build Mode

You are running inside an Owloop autonomous loop (Context A).

Read `.specify/memory/constitution.md` — it contains all project principles, workflow
instructions, work sources, and completion signal requirements.

Find the highest-priority incomplete work item, implement it completely, verify all
acceptance criteria, commit and push, then output `<promise>DONE</promise>`.
"""

PLAN_PROMPT = """\
# Owloop — Planning Mode

You are running inside an Owloop autonomous loop in planning mode.

Read `.specify/memory/constitution.md` for project principles.

Study `specs/` and compare against the current codebase (gap analysis).
Create or update `IMPLEMENTATION_PLAN.md` with a prioritized task breakdown.
Do NOT implement anything.

When the plan is complete, output `<promise>DONE</promise>`.
"""

EventCallback = Callable[[str, dict], None]


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _file_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


@dataclass
class EngineConfig:
    project_dir: Path
    mode: str = "build"  # "build" | "plan"
    max_iterations: int = 0  # 0 = unlimited
    worktree: bool = True
    max_consecutive_failures: int = 3
    tail_lines: int = 5


@dataclass
class IterationResult:
    iteration: int
    success: bool
    done_signal: str | None
    returncode: int
    timed_out: bool
    log_file: Path


@dataclass
class RunSummary:
    iterations: int
    branch: str
    cwd: Path
    main_repo_dir: Path
    stopped_reason: str
    issues: list[str] | None = None


class OwloopEngine:
    def __init__(self, config: EngineConfig, adapter: AgentAdapter, on_event: EventCallback | None = None):
        self.config = config
        self.adapter = adapter
        self.on_event = on_event or (lambda *_args: None)
        self.cwd = config.project_dir
        self.main_repo_dir = config.project_dir
        self.log_dir = config.project_dir / "logs"
        self.session_log: Path | None = None

    def _emit(self, kind: str, **data) -> None:
        self.on_event(kind, data)

    def _run_git(self, *args: str, check: bool = False) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args],
            cwd=self.cwd,
            capture_output=True,
            text=True,
            check=check,
        )

    def _log_line(self, text: str) -> None:
        if self.session_log is not None:
            with self.session_log.open("a") as f:
                f.write(text + "\n")

    def _is_git_repo(self) -> bool:
        return self._run_git("rev-parse", "--is-inside-work-tree").returncode == 0

    def _is_dirty(self) -> bool:
        return bool(self._run_git("status", "--porcelain").stdout.strip())

    def _resolve_main_repo_dir(self) -> Path:
        if not self._is_git_repo():
            return self.config.project_dir
        result = self._run_git("worktree", "list", "--porcelain")
        for line in result.stdout.splitlines():
            if line.startswith("worktree "):
                return Path(line[len("worktree ") :])
        return self.config.project_dir

    def preflight_check(self) -> list[str]:
        """Environment sanity checks that must pass before the loop may start."""
        issues: list[str] = self.adapter.preflight()

        if not self._is_git_repo():
            issues.append("当前目录不是 git 仓库")

        specs_dir = self.cwd / "specs"
        has_plan = (self.cwd / "IMPLEMENTATION_PLAN.md").is_file()
        if not has_plan and not spec_queue.get_root_specs(specs_dir):
            issues.append("specs/ 目录下没有 .md 文件，且没有 IMPLEMENTATION_PLAN.md")

        return issues

    def _copy_claude_config(self, worktree_path: Path) -> None:
        """Copy the main repo's .claude/ into a new worktree so project-level
        permissions/settings still apply there."""
        claude_dir = self.main_repo_dir / ".claude"
        target = worktree_path / ".claude"
        if claude_dir.is_dir() and not target.exists():
            shutil.copytree(claude_dir, target)
            self._emit("claude_config_copied", path=str(target))

    def setup_worktree(self) -> bool:
        """Create/enter an isolated git worktree unless disabled or already inside one.

        Returns False if the run should abort entirely (user declined to
        continue against a dirty main-repo workspace).
        """
        if not self.config.worktree:
            self._emit("worktree_skipped", reason="disabled")
            return True

        if not self._is_git_repo():
            self._emit("worktree_skipped", reason="not_a_git_repo")
            return True

        if self.cwd != self.main_repo_dir:
            self._emit("worktree_already_active", path=str(self.cwd))
            return True

        if self._is_dirty():
            self._emit("dirty_workspace_warning")
            if sys.stdin.isatty():
                try:
                    reply = input("> ").strip().lower() or "n"
                except EOFError:
                    reply = "n"
                if not reply.startswith("y"):
                    self._emit("dirty_workspace_declined")
                    return False
            else:
                self._emit("dirty_workspace_noninteractive_continue")

        if not sys.stdin.isatty():
            self._emit("worktree_skipped", reason="non_interactive")
            return True

        self._emit("worktree_prompt")
        try:
            reply = input("> ").strip() or "Y"
        except EOFError:
            reply = "Y"

        if not reply.lower().startswith("y"):
            self._emit("worktree_declined")
            return True

        wt_date = datetime.now().strftime("%Y%m%d")
        wt_branch = f"owloop/{wt_date}"
        wt_path = (
            self.config.project_dir.parent
            / f"{self.config.project_dir.name}-owloop-wt"
            / f"owloop-{wt_date}"
        )

        self._emit("worktree_creating", path=str(wt_path), branch=wt_branch)

        if wt_path.is_dir():
            self.cwd = wt_path
            self._emit("worktree_reused", path=str(wt_path))
            self._copy_claude_config(wt_path)
            return True

        created = self._run_git("worktree", "add", str(wt_path), "-b", wt_branch)
        if created.returncode == 0:
            self.cwd = wt_path
            self._emit("worktree_created", path=str(wt_path), branch=wt_branch)
            self._copy_claude_config(wt_path)
            return True

        reused = self._run_git("worktree", "add", str(wt_path), wt_branch)
        if reused.returncode == 0:
            self.cwd = wt_path
            self._emit("worktree_branch_reused", path=str(wt_path), branch=wt_branch)
            self._copy_claude_config(wt_path)
            return True

        self._emit("worktree_failed", stderr=created.stderr)
        return True

    def _write_prompt_files(self) -> None:
        (self.cwd / "PROMPT_build.md").write_text(BUILD_PROMPT)
        (self.cwd / "PROMPT_plan.md").write_text(PLAN_PROMPT)

    def _current_branch(self) -> str:
        result = self._run_git("branch", "--show-current")
        return result.stdout.strip() or "main"

    def _spec_status(self) -> dict:
        specs_dir = self.cwd / "specs"
        has_plan = (self.cwd / "IMPLEMENTATION_PLAN.md").is_file()
        specs = spec_queue.get_root_specs(specs_dir)
        incomplete = spec_queue.get_incomplete_root_specs(specs_dir)
        return {
            "has_plan": has_plan,
            "has_specs": len(specs) > 0,
            "spec_count": len(specs),
            "incomplete_count": len(incomplete),
            "specs": [
                {"name": p.name, "done": p not in incomplete} for p in specs
            ],
            "first_incomplete": incomplete[0].name if incomplete else None,
        }

    def _push(self, branch: str) -> None:
        pushed = self._run_git("push", "origin", branch)
        if pushed.returncode != 0:
            ahead = self._run_git("log", f"origin/{branch}..HEAD", "--oneline")
            if ahead.stdout.strip():
                self._emit("push_retry", branch=branch)
                self._run_git("push", "-u", "origin", branch)

    def run_iteration(self, iteration: int) -> IterationResult:
        prompt_file = self.cwd / (
            "PROMPT_plan.md" if self.config.mode == "plan" else "PROMPT_build.md"
        )
        log_file = self.log_dir / (
            f"owloop_{self.config.mode}_iter_{iteration}_{_file_timestamp()}.log"
        )

        self._emit("iteration_start", iteration=iteration, timestamp=_timestamp())

        prompt_text = prompt_file.read_text()

        with log_file.open("w") as log_f:

            def _on_line(line: str) -> None:
                log_f.write(line + "\n")
                self._log_line(line)
                self._emit("output_line", line=line)

            result = self.adapter.run(prompt_text, cwd=self.cwd, on_line=_on_line)

        tail = "\n".join(result.stdout.splitlines()[-self.config.tail_lines :])

        if result.timed_out:
            self._emit("agent_timeout", iteration=iteration)
        elif not result.success:
            self._emit("agent_failed", returncode=result.returncode, tail=tail)
        elif result.has_completion_signal:
            self._emit("done_signal", signal=result.done_signal)
        else:
            self._emit("no_done_signal", tail=tail)

        success = result.success and result.has_completion_signal

        return IterationResult(
            iteration=iteration,
            success=success,
            done_signal=result.done_signal,
            returncode=result.returncode,
            timed_out=result.timed_out,
            log_file=log_file,
        )

    def run(self) -> RunSummary:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.main_repo_dir = self._resolve_main_repo_dir()
        self.session_log = self.log_dir / f"owloop_{self.config.mode}_session_{_file_timestamp()}.log"

        issues = self.preflight_check()
        if issues:
            self._emit("preflight_failed", issues=issues)
            return RunSummary(
                iterations=0,
                branch="",
                cwd=self.cwd,
                main_repo_dir=self.main_repo_dir,
                stopped_reason="preflight_failed",
                issues=issues,
            )

        if not self.setup_worktree():
            return RunSummary(
                iterations=0,
                branch=self._current_branch(),
                cwd=self.cwd,
                main_repo_dir=self.main_repo_dir,
                stopped_reason="dirty_workspace_declined",
            )

        self._write_prompt_files()

        branch = self._current_branch()
        status = self._spec_status()

        self._emit(
            "session_info",
            mode=self.config.mode,
            model=self.adapter.name,
            branch=branch,
            cwd=str(self.cwd),
            main_repo_dir=str(self.main_repo_dir),
            session_log=str(self.session_log),
            max_iterations=self.config.max_iterations,
            **status,
        )

        if (
            self.config.mode == "build"
            and not status["has_plan"]
            and status["has_specs"]
            and status["incomplete_count"] == 0
        ):
            self._emit("all_specs_complete", spec_count=status["spec_count"])
            return RunSummary(
                iterations=0,
                branch=branch,
                cwd=self.cwd,
                main_repo_dir=self.main_repo_dir,
                stopped_reason="all_specs_complete",
            )

        iteration = 0
        consecutive_failures = 0
        stopped_reason = "max_iterations"

        try:
            while True:
                if self.config.max_iterations > 0 and iteration >= self.config.max_iterations:
                    break

                iteration += 1
                result = self.run_iteration(iteration)

                if result.success:
                    consecutive_failures = 0
                    if self.config.mode == "plan":
                        stopped_reason = "plan_complete"
                        self._emit("plan_complete")
                        break
                else:
                    consecutive_failures += 1
                    if consecutive_failures >= self.config.max_consecutive_failures:
                        self._emit("stuck_warning", consecutive_failures=consecutive_failures)
                        consecutive_failures = 0

                self._push(branch)
                self._emit(
                    "iteration_end",
                    iteration=iteration,
                    success=result.success,
                    specs=self._spec_status()["specs"],
                )
                time.sleep(2)
        except KeyboardInterrupt:
            stopped_reason = "interrupted"
            self._emit("interrupted", iteration=iteration)

        return RunSummary(
            iterations=iteration,
            branch=branch,
            cwd=self.cwd,
            main_repo_dir=self.main_repo_dir,
            stopped_reason=stopped_reason,
        )
