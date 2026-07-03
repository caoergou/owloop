"""Python port of scripts/owloop.sh — the autonomous build/plan loop engine.

The engine spawns one fresh ``claude -p`` process per iteration, watches its
output for the ``<promise>DONE</promise>`` completion signal, commits/pushes
on success, and retries (up to a consecutive-failure limit) otherwise.

All UI concerns (TUI, plain console) live outside this module: the engine
only reports progress through the ``on_event(kind, data)`` callback so it can
be driven headless (tests, CI) or rendered any way the caller likes.
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from owloop import spec_queue

DONE_SIGNAL_RE = re.compile(r"<promise>(?:ALL_)?DONE</promise>")

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
    model: str = "claude-sonnet-5"
    claude_cmd: str = "claude"
    worktree: bool = True
    max_consecutive_failures: int = 3
    tail_lines: int = 5


@dataclass
class IterationResult:
    iteration: int
    success: bool
    done_signal: str | None
    returncode: int
    log_file: Path


@dataclass
class RunSummary:
    iterations: int
    branch: str
    cwd: Path
    main_repo_dir: Path
    stopped_reason: str


class OwloopEngine:
    def __init__(self, config: EngineConfig, on_event: EventCallback | None = None):
        self.config = config
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

    def _resolve_main_repo_dir(self) -> Path:
        if not self._is_git_repo():
            return self.config.project_dir
        result = self._run_git("worktree", "list", "--porcelain")
        for line in result.stdout.splitlines():
            if line.startswith("worktree "):
                return Path(line[len("worktree ") :])
        return self.config.project_dir

    def setup_worktree(self) -> None:
        """Create/enter an isolated git worktree unless disabled or already inside one."""
        if not self.config.worktree:
            self._emit("worktree_skipped", reason="disabled")
            return

        if not self._is_git_repo():
            self._emit("worktree_skipped", reason="not_a_git_repo")
            return

        if self.cwd != self.main_repo_dir:
            self._emit("worktree_already_active", path=str(self.cwd))
            return

        if not sys.stdin.isatty():
            self._emit("worktree_skipped", reason="non_interactive")
            return

        self._emit("worktree_prompt")
        try:
            reply = input("> ").strip() or "Y"
        except EOFError:
            reply = "Y"

        if not reply.lower().startswith("y"):
            self._emit("worktree_declined")
            return

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
            return

        created = self._run_git("worktree", "add", str(wt_path), "-b", wt_branch)
        if created.returncode == 0:
            self.cwd = wt_path
            self._emit("worktree_created", path=str(wt_path), branch=wt_branch)
            return

        reused = self._run_git("worktree", "add", str(wt_path), wt_branch)
        if reused.returncode == 0:
            self.cwd = wt_path
            self._emit("worktree_branch_reused", path=str(wt_path), branch=wt_branch)
            return

        self._emit("worktree_failed", stderr=created.stderr)

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

    def _run_claude(self, prompt_file: Path, log_file: Path) -> tuple[int, str]:
        cmd = [
            self.config.claude_cmd,
            "-p",
            "--model",
            self.config.model,
            "--permission-mode",
            "auto",
        ]
        prompt_text = prompt_file.read_text()

        output_lines: list[str] = []
        with log_file.open("w") as log_f:
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=self.cwd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    start_new_session=True,
                )
            except FileNotFoundError:
                self._emit("claude_not_found", cmd=self.config.claude_cmd)
                return 127, ""

            try:
                assert proc.stdin is not None and proc.stdout is not None
                proc.stdin.write(prompt_text)
                proc.stdin.close()

                for line in proc.stdout:
                    line = line.rstrip("\n")
                    output_lines.append(line)
                    log_f.write(line + "\n")
                    self._log_line(line)
                    self._emit("output_line", line=line)

                proc.wait()
            except KeyboardInterrupt:
                # start_new_session=True put claude (and any children it spawns) in
                # its own process group, so kill that whole group rather than just
                # the direct child — otherwise grandchildren can be orphaned.
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                raise

            return proc.returncode, "\n".join(output_lines)

    def run_iteration(self, iteration: int) -> IterationResult:
        prompt_file = self.cwd / (
            "PROMPT_plan.md" if self.config.mode == "plan" else "PROMPT_build.md"
        )
        log_file = self.log_dir / (
            f"owloop_{self.config.mode}_iter_{iteration}_{_file_timestamp()}.log"
        )

        self._emit("iteration_start", iteration=iteration, timestamp=_timestamp())

        returncode, output = self._run_claude(prompt_file, log_file)

        done_signal = None
        success = False

        if returncode == 0:
            match = DONE_SIGNAL_RE.search(output)
            if match:
                done_signal = match.group(0)
                success = True
                self._emit("done_signal", signal=done_signal)
            else:
                self._emit(
                    "no_done_signal",
                    tail="\n".join(output.splitlines()[-self.config.tail_lines :]),
                )
        else:
            self._emit(
                "claude_failed",
                returncode=returncode,
                tail="\n".join(output.splitlines()[-self.config.tail_lines :]),
            )

        return IterationResult(
            iteration=iteration,
            success=success,
            done_signal=done_signal,
            returncode=returncode,
            log_file=log_file,
        )

    def run(self) -> RunSummary:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.main_repo_dir = self._resolve_main_repo_dir()
        self.session_log = self.log_dir / f"owloop_{self.config.mode}_session_{_file_timestamp()}.log"

        if shutil.which(self.config.claude_cmd) is None:
            self._emit("claude_cli_missing", cmd=self.config.claude_cmd)
            return RunSummary(
                iterations=0,
                branch="",
                cwd=self.cwd,
                main_repo_dir=self.main_repo_dir,
                stopped_reason="claude_cli_missing",
            )

        self.setup_worktree()
        self._write_prompt_files()

        branch = self._current_branch()
        status = self._spec_status()

        self._emit(
            "session_info",
            mode=self.config.mode,
            model=self.config.model,
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
