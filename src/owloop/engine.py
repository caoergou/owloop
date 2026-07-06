"""Python port of scripts/owloop.sh — the autonomous build loop engine.

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

import json
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from owloop import spec_queue
from owloop.adapters import AgentAdapter
from owloop.learnings import (
    append_learning,
    extract_learnings,
    format_learnings_for_prompt,
    load_learnings,
)
from owloop.paths import resolve_logs_dir, resolve_owloop_dir, resolve_specs_dir
from owloop.promise import parse_promise_signal
from owloop.sleep_inhibitor import SleepInhibitor
from owloop.subagents import SubagentOrchestrator

BUILD_PROMPT = """\
# Owloop — Build Mode

You are running inside an Owloop autonomous loop.

Read these files if they exist (in order):
1. `AGENTS.md` — agent instructions for this project
2. `CLAUDE.md` — coding conventions, architecture rules, tool commands

Find the highest-priority incomplete work item in specs/, implement it completely,
verify all acceptance criteria by running the shell commands specified in the spec,
add a `**Status**: COMPLETE` line near the top of that spec's markdown file
(this is how the next iteration knows to skip it — omitting this step means the
loop will pick the same spec again), commit and push, then output
`<promise>DONE</promise>`.

If you hit an external blocker (missing API key, unavailable dependency), output
`<promise>BLOCKED:reason</promise>` and the loop will stop. If you need a human
decision before continuing, output `<promise>DECIDE:question</promise>` and the
loop will stop to ask for guidance.

If you discover a useful operational fact during this iteration (e.g., "tests
require a running database", "use poetry not pip"), wrap it in
`<learning>...</learning>` tags. It will be saved to `.owloop/learnings.md` and
loaded into the next iteration so you do not have to rediscover it.

Before implementing, search the codebase for existing implementations — do not
assume something doesn't exist without checking.

ONLY modify files within the scope described in the spec's Requirements section.
Do NOT touch files listed in the spec's Exclusions section.
Do NOT modify, delete, or comment out existing tests.

## Final output requirement

After you have committed and pushed, the very last line of your response must be
exactly one of the following promise signals and nothing else on that line:

- `<promise>DONE</promise>` when the spec is fully implemented and verified.
- `<promise>BLOCKED:reason</promise>` when an external blocker stops you.
- `<promise>DECIDE:question</promise>` when you need a human decision.

Do not wrap the promise in a code block, do not add explanatory text after it,
and do not omit it. The loop relies on this exact line to detect completion.
"""

VERIFIER_PROMPT = """\
# Owloop — Verification Mode

You are an independent verifier. You did NOT write the code. Your job is to
check whether the highest-priority incomplete spec in specs/ has actually been
completed.

1. Read the spec file (including Requirements and Acceptance Criteria).
2. Run each acceptance criterion command exactly as written.
3. Check the output matches the expected result described in the spec.
4. If ALL criteria pass, output `<promise>PASS</promise>`.
5. If ANY criterion fails, output `<promise>FAIL: describe what failed and why</promise>`.

Do NOT modify files. Only run read-only verification commands. Be concise.
"""

EventCallback = Callable[[str, dict], None]


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _file_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


@dataclass
class EngineConfig:
    project_dir: Path
    max_iterations: int = 0  # 0 = unlimited
    max_duration_minutes: int = 0  # 0 = unlimited
    max_tokens: int = 0  # 0 = unlimited
    idle_timeout: float = 3600  # seconds, passed to adapter
    worktree: bool = True
    max_consecutive_failures: int = 3
    base_retry_delay: float = 2.0
    max_retry_delay: float = 60.0
    fix_loop_threshold: int = 3
    tail_lines: int = 5
    use_subagents: bool = False
    subagent_file_threshold: int = 3
    # Optional confirm callbacks so a caller (e.g. the TUI) can render its own
    # styled prompt instead of the engine falling back to raw input(). When
    # None, setup_worktree() keeps the original input()-based behavior.
    confirm_dirty: Callable[[], bool] | None = None
    confirm_worktree: Callable[[], bool] | None = None
    verifier_adapter: AgentAdapter | None = None
    # Session identity. When None, the engine generates a fresh id. When
    # ``resume`` is True, the engine reuses the latest recorded session.
    session_id: str | None = None
    resume: bool = False


@dataclass
class IterationResult:
    iteration: int
    success: bool
    done_signal: str | None
    returncode: int
    timed_out: bool
    log_file: Path
    tokens_used: int = 0
    summary: str = ""
    promise_state: str = ""
    promise_payload: str = ""
    stdout: str = ""


@dataclass
class RunSummary:
    iterations: int
    branch: str
    cwd: Path
    main_repo_dir: Path
    stopped_reason: str
    issues: list[str] | None = None
    tokens_used: int = 0
    blocker: str | None = None
    decision_question: str | None = None
    session_id: str = ""
    resumed_from_session: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "iterations": self.iterations,
            "branch": self.branch,
            "cwd": str(self.cwd),
            "main_repo_dir": str(self.main_repo_dir),
            "stopped_reason": self.stopped_reason,
            "issues": self.issues,
            "tokens_used": self.tokens_used,
            "blocker": self.blocker,
            "decision_question": self.decision_question,
            "session_id": self.session_id,
            "resumed_from_session": self.resumed_from_session,
        }


class OwloopEngine:
    # Class-level default so ``session_id`` is discoverable on the class itself
    # (e.g. via ``dir(OwloopEngine)``) even before an instance resolves one.
    session_id: str | None = None

    def __init__(self, config: EngineConfig, adapter: AgentAdapter, on_event: EventCallback | None = None):
        self.config = config
        self.adapter = adapter
        self.verifier_adapter = config.verifier_adapter
        self.on_event = on_event or (lambda *_args: None)
        self.cwd = config.project_dir
        self.main_repo_dir = config.project_dir
        self.session_log: Path | None = None
        self._recent_file_sets: list[set[str]] = []
        self.tokens_used = 0
        self.session_id = config.session_id
        self.resumed_from_session: str | None = None
        self._resumed_iterations = 0
        self._resumed_elapsed_seconds = 0.0
        self._run_start_time: float | None = None

    @property
    def owloop_dir(self) -> Path:
        """Resolved owloop metadata directory against the current cwd."""
        return resolve_owloop_dir(self.cwd)

    @property
    def specs_dir(self) -> Path:
        """Resolved specs directory against the current cwd."""
        return resolve_specs_dir(self.cwd)

    @property
    def log_dir(self) -> Path:
        """Resolved logs directory against the current cwd."""
        return resolve_logs_dir(self.cwd)

    def _emit(self, kind: str, **data: Any) -> None:
        self.on_event(kind, data)
        self._log_event(kind, data)

    def _events_log_path(self) -> Path:
        """Path to the structured, append-only JSON Lines event log."""
        return self.log_dir / "events.jsonl"

    def _log_event(self, kind: str, data: dict[str, Any]) -> None:
        """Append one JSON line for this event; creates the log lazily."""
        path = self._events_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now().isoformat(),
            "session_id": self.session_id,
            "kind": kind,
            "data": data,
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")

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
            with self.session_log.open("a", encoding="utf-8") as f:
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
            issues.append("current directory is not a git repository")

        if not spec_queue.get_root_specs(self.specs_dir):
            issues.append("no .md files in specs/")

        return issues

    def _copy_dot_dir(self, worktree_path: Path, name: str, event_name: str) -> None:
        """Copy a dot-directory from the main repo into a new worktree.

        Git does not track ``.owloop/`` or ``.claude/`` by default, so the
        worktree needs its own copies for prompts, specs, and agent settings.
        If the target already exists (e.g., a tracked ``.owloop/specs/`` was
        materialized by ``git worktree add``), we still need to sync the latest
        contents from the main repo so new/untracked specs and prompts show up.
        """
        source = self.main_repo_dir / name
        target = worktree_path / name
        if not source.is_dir():
            return
        if target.exists():
            shutil.copytree(source, target, dirs_exist_ok=True)
            self._emit(f"{event_name}_synced", path=str(target))
        else:
            shutil.copytree(source, target)
            self._emit(event_name, path=str(target))

    def _copy_claude_config(self, worktree_path: Path) -> None:
        """Copy the main repo's .claude/ into a new worktree so project-level
        permissions/settings still apply there."""
        self._copy_dot_dir(worktree_path, ".claude", "claude_config_copied")

    def _copy_owloop_dir(self, worktree_path: Path) -> None:
        """Copy the main repo's .owloop/ into a new worktree.

        This keeps specs, logs, and prompt files in the worktree so the loop
        can read and write them without touching the original checkout.
        """
        self._copy_dot_dir(worktree_path, ".owloop", "owloop_dir_copied")

    def _session_file(self) -> Path:
        """Path to the persisted session descriptor in the main repo.

        Uses ``resolve_owloop_dir`` (like the rest of the engine) instead of
        hardcoding ``.owloop/`` so that persisting session progress never
        creates that directory as a side effect on legacy projects that
        haven't materialized it yet — doing so would flip ``resolve_owloop_dir``
        from its legacy fallback to the modern path mid-run and break other
        `.owloop`-relative reads/writes (e.g. the build prompt file).
        """
        return resolve_owloop_dir(self.main_repo_dir) / "logs" / "session_latest.json"

    def _load_session(self) -> dict[str, str] | None:
        """Load the most recent session descriptor if it exists."""
        path = self._session_file()
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "branch" in data and "path" in data:
                return data
        except (json.JSONDecodeError, OSError):
            return None
        return None

    def _save_session(self, session_id: str, branch: str, path: Path) -> None:
        """Persist a freshly created session so ``--resume`` can find it later."""
        session_path = self._session_file()
        session_path.parent.mkdir(parents=True, exist_ok=True)
        session_path.write_text(
            json.dumps(
                {
                    "session_id": session_id,
                    "branch": branch,
                    "path": str(path),
                    "started_at": datetime.now().isoformat(),
                    "status": "running",
                    "iterations": 0,
                    "tokens_used": 0,
                    "elapsed_seconds": 0.0,
                    "current_spec": None,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def _init_session(self) -> None:
        """Resolve this run's session id and, when resuming, restore counters.

        Runs before ``setup_worktree`` so session identity and budget
        carry-over apply whether or not worktree isolation is enabled.
        Never raises — ``_resolve_worktree_session`` remains the place that
        surfaces a "nothing to resume" error when worktree isolation is on.
        """
        if not self.config.resume:
            self.session_id = self.config.session_id or uuid.uuid4().hex[:8]
            return

        session = self._load_session()
        if session is not None:
            self.session_id = session.get("session_id")
            self.resumed_from_session = self.session_id
            self.tokens_used = int(session.get("tokens_used", 0))
            self._resumed_iterations = int(session.get("iterations", 0))
            self._resumed_elapsed_seconds = float(session.get("elapsed_seconds", 0.0))
            return

        branch = self._latest_owloop_branch()
        if branch is not None:
            self.session_id = branch.split("/", 1)[1].split("-", 1)[1]
            self.resumed_from_session = self.session_id
            return

        # Nothing to resume: fall back to a fresh session id so the run still
        # has one. If worktree isolation is enabled, setup_worktree() will
        # raise its own "no previous session found" error shortly after this.
        self.session_id = self.config.session_id or uuid.uuid4().hex[:8]

    def _persist_session_progress(
        self, *, status: str, iterations: int, current_spec: str | None
    ) -> None:
        """Update the persisted session record with live progress and status."""
        if not self.session_id:
            return
        path = self._session_file()
        data: dict[str, Any] = {}
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}
        data.setdefault("session_id", self.session_id)
        data.setdefault("branch", self._current_branch())
        data.setdefault("path", str(self.cwd))
        data.setdefault("started_at", datetime.now().isoformat())
        data["status"] = status
        data["iterations"] = iterations
        data["tokens_used"] = self.tokens_used
        data["elapsed_seconds"] = (
            time.monotonic() - self._run_start_time
            if self._run_start_time is not None
            else data.get("elapsed_seconds", 0.0)
        )
        data["current_spec"] = current_spec
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _branch_exists(self, branch: str) -> bool:
        """Return True if a local branch with the given name exists."""
        result = self._run_git("show-ref", "--verify", f"refs/heads/{branch}")
        return result.returncode == 0

    def _latest_owloop_branch(self) -> str | None:
        """Return the most recently committed owloop/* branch, if any."""
        result = self._run_git(
            "branch",
            "--list",
            "owloop/*",
            "--format=%(refname:short)",
            "--sort=-committerdate",
        )
        branches = [b for b in result.stdout.splitlines() if b.strip()]
        return branches[0] if branches else None

    def _resolve_worktree_session(self) -> tuple[str, str, Path]:
        """Pick or resume a session id and derive branch/worktree path.

        Returns a tuple of (session_id, branch_name, worktree_path).
        """
        wt_date = datetime.now().strftime("%Y%m%d")
        wt_base = self.config.project_dir.parent / f"{self.config.project_dir.name}-owloop-wt"

        if self.config.resume:
            session = self._load_session()
            if session is None:
                branch = self._latest_owloop_branch()
                if branch is None:
                    raise RuntimeError(
                        "--resume requested but no previous owloop session found."
                    )
                # Branch format: owloop/<date>-<session_id>
                session_id = branch.split("/", 1)[1].split("-", 1)[1]
                wt_path = wt_base / f"owloop-{branch.split('/', 1)[1]}"
            else:
                session_id = session["session_id"]
                branch = session["branch"]
                wt_path = Path(session["path"])
            self.session_id = session_id
            return session_id, branch, wt_path

        # Reuse the id ``_init_session`` already resolved (if any) so this run
        # has a single consistent session id, instead of minting a second one.
        session_id = self.session_id or self.config.session_id or uuid.uuid4().hex[:8]
        branch = f"owloop/{wt_date}-{session_id}"
        wt_path = wt_base / f"owloop-{wt_date}-{session_id}"

        # Guard against an extremely unlikely collision.
        while self._branch_exists(branch):
            session_id = uuid.uuid4().hex[:8]
            branch = f"owloop/{wt_date}-{session_id}"
            wt_path = wt_base / f"owloop-{wt_date}-{session_id}"

        self._save_session(session_id, branch, wt_path)
        self.session_id = session_id
        return session_id, branch, wt_path

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
            if self.config.confirm_dirty is not None:
                if not self.config.confirm_dirty():
                    self._emit("dirty_workspace_declined")
                    return False
            elif sys.stdin.isatty():
                try:
                    reply = input("> ").strip().lower() or "n"
                except EOFError:
                    reply = "n"
                if not reply.startswith("y"):
                    self._emit("dirty_workspace_declined")
                    return False
            else:
                self._emit("dirty_workspace_noninteractive_continue")

        if self.config.confirm_worktree is not None:
            self._emit("worktree_prompt")
            if not self.config.confirm_worktree():
                self._emit("worktree_declined")
                return True
        elif sys.stdin.isatty():
            self._emit("worktree_prompt")
            try:
                reply = input("> ").strip() or "Y"
            except EOFError:
                reply = "Y"

            if not reply.lower().startswith("y"):
                self._emit("worktree_declined")
                return True
        else:
            # Headless/CI/agent invocation: there's no one to answer the prompt, and
            # skipping isolation here is the one outcome that defeats the whole point
            # of an *unattended* loop. Default to creating the worktree rather than
            # falling through to the (possibly dirty) main repo.
            self._emit("worktree_auto_created", reason="non_interactive")

        session_id, wt_branch, wt_path = self._resolve_worktree_session()
        self.session_id = session_id

        self._emit("worktree_creating", path=str(wt_path), branch=wt_branch)

        if wt_path.is_dir():
            self.cwd = wt_path
            self._emit("worktree_reused", path=str(wt_path), branch=wt_branch)
            self._copy_claude_config(wt_path)
            self._copy_owloop_dir(wt_path)
            return True

        wt_base = wt_path.parent
        wt_base.mkdir(parents=True, exist_ok=True)

        # If the session branch already exists (e.g., from a previous resume),
        # attach a new worktree to it; otherwise create a fresh branch.
        if self._branch_exists(wt_branch):
            attached = self._run_git("worktree", "add", str(wt_path), wt_branch)
            if attached.returncode == 0:
                self.cwd = wt_path
                self._emit("worktree_branch_reused", path=str(wt_path), branch=wt_branch)
                self._copy_claude_config(wt_path)
                self._copy_owloop_dir(wt_path)
                return True
        else:
            created = self._run_git("worktree", "add", str(wt_path), "-b", wt_branch)
            if created.returncode == 0:
                self.cwd = wt_path
                self._emit("worktree_created", path=str(wt_path), branch=wt_branch)
                self._copy_claude_config(wt_path)
                self._copy_owloop_dir(wt_path)
                return True

        self._emit("worktree_failed", stderr=f"could not create or attach worktree for {wt_branch}")
        return True

    def _write_prompt_file(self) -> None:
        owloop_dir = resolve_owloop_dir(self.cwd)
        (owloop_dir / "PROMPT_build.md").write_text(BUILD_PROMPT, encoding="utf-8")

    def _current_branch(self) -> str:
        result = self._run_git("branch", "--show-current")
        return result.stdout.strip() or "main"

    def _spec_status(self) -> dict:
        specs = spec_queue.get_root_specs(self.specs_dir)
        incomplete = spec_queue.get_incomplete_root_specs(self.specs_dir)
        # Dependency-aware pick; fall back to raw filename order only when every
        # incomplete spec is blocked (e.g. a dependency cycle among them).
        next_spec = spec_queue.get_next_ready_spec(self.specs_dir) or (
            incomplete[0] if incomplete else None
        )
        return {
            "has_specs": len(specs) > 0,
            "spec_count": len(specs),
            "incomplete_count": len(incomplete),
            "specs": [
                {"name": p.name, "done": p not in incomplete} for p in specs
            ],
            "first_incomplete": next_spec.name if next_spec else None,
        }

    def _check_fix_loop(self) -> bool:
        """Detect when the same files keep getting modified without progress.

        Returns True when the loop should stop because the same files keep
        changing without making progress.
        """
        result = self._run_git("diff", "--name-only", "HEAD~1", "HEAD")
        if result.returncode != 0:
            return False
        changed = {f.strip() for f in result.stdout.splitlines() if f.strip()}
        if not changed:
            return False
        self._recent_file_sets.append(changed)
        threshold = self.config.fix_loop_threshold
        if len(self._recent_file_sets) < threshold:
            return False
        window = self._recent_file_sets[-threshold:]
        repeated = set.intersection(*window)
        if repeated:
            self._emit("fix_loop_warning", files=sorted(repeated), consecutive=threshold)
            self._emit(
                "fix_loop_blocked",
                files=sorted(repeated),
                reason="same files modified repeatedly; spec needs to be split manually",
            )
            return True
        if len(self._recent_file_sets) > threshold * 2:
            self._recent_file_sets = self._recent_file_sets[-threshold * 2:]
        return False

    def _read_run_notes(self) -> str | None:
        path = self.cwd / "run-notes.md"
        if path.is_file():
            return path.read_text(encoding="utf-8")
        return None

    def _read_steering(self) -> str | None:
        path = self.cwd / "STEERING.md"
        if path.is_file():
            return path.read_text(encoding="utf-8")
        return None

    def _build_prompt_with_context(self, prompt_text: str) -> str:
        """Prepend run-notes, STEERING.md, and learnings to the iteration prompt."""
        sections: list[str] = []

        steering = self._read_steering()
        if steering is not None:
            self._emit("steering_loaded", path=str(self.cwd / "STEERING.md"))
            sections.append(
                "The user has provided mid-flight guidance in STEERING.md. "
                "Follow these instructions for this iteration.\n\n"
                f"{steering}"
            )

        notes = self._read_run_notes()
        if notes is not None:
            self._emit("run_notes_loaded", path=str(self.cwd / "run-notes.md"))
            sections.append(
                "The following notes were recorded during previous iterations of this run. "
                "Read them to avoid repeating mistakes.\n\n"
                f"{notes}"
            )

        learnings_text = format_learnings_for_prompt(load_learnings(self.cwd))
        if learnings_text:
            self._emit("learnings_loaded", path=str(self.cwd / ".owloop" / "learnings.md"))
            sections.append(learnings_text)

        if not sections:
            return prompt_text

        context = "\n\n---\n\n".join(sections)
        return f"{context}\n\n---\n\n{prompt_text}"

    def _append_run_note(
        self, iteration: int, success: bool, summary: str, learning: str = ""
    ) -> None:
        """Append a concise cross-iteration note to run-notes.md."""
        run_notes_path = self.cwd / "run-notes.md"
        status = "success" if success else "failure"
        entry = (
            f"## Iteration {iteration} — {_timestamp()}\n"
            f"- Status: {status}\n"
            f"- Summary: {summary}\n"
            f"- Learning: {learning}\n"
        )
        prefix = "\n" if run_notes_path.is_file() and run_notes_path.stat().st_size > 0 else ""
        with run_notes_path.open("a", encoding="utf-8") as f:
            f.write(prefix + entry)
        self._emit(
            "run_note_appended",
            path=str(run_notes_path),
            iteration=iteration,
            success=success,
        )

    def _push(self, branch: str) -> None:
        pushed = self._run_git("push", "origin", branch)
        if pushed.returncode != 0:
            ahead = self._run_git("log", f"origin/{branch}..HEAD", "--oneline")
            if ahead.stdout.strip():
                self._emit("push_retry", branch=branch)
                self._run_git("push", "-u", "origin", branch)

    def run_iteration(self, iteration: int) -> IterationResult:
        owloop_dir = resolve_owloop_dir(self.cwd)
        prompt_file = owloop_dir / "PROMPT_build.md"
        log_file = self.log_dir / (
            f"owloop_build_iter_{iteration}_{_file_timestamp()}.log"
        )

        self._emit("iteration_start", iteration=iteration, timestamp=_timestamp())

        prompt_text = self._build_prompt_with_context(
            prompt_file.read_text(encoding="utf-8")
        )

        with log_file.open("w", encoding="utf-8") as log_f:

            def _on_line(line: str) -> None:
                log_f.write(line + "\n")
                self._log_line(line)
                self._emit("output_line", line=line)

            if self.config.use_subagents:
                orchestrator = SubagentOrchestrator(
                    self.adapter, self.verifier_adapter, self.cwd, on_line=_on_line
                )
                result = orchestrator.run()
            else:
                result = self.adapter.run(prompt_text, cwd=self.cwd, on_line=_on_line)

        tail = "\n".join(result.stdout.splitlines()[-self.config.tail_lines :])
        parsed = parse_promise_signal(result.stdout)
        promise_state = parsed[0] if parsed else ""
        promise_payload = parsed[1] if parsed else ""

        self.tokens_used += result.tokens_used
        self._emit("tokens_update", iteration=iteration, tokens_used=result.tokens_used, total_tokens=self.tokens_used)

        if result.timed_out:
            self._emit("agent_timeout", iteration=iteration)
        elif not result.success:
            self._emit("agent_failed", returncode=result.returncode, tail=tail)
        elif promise_state == "DONE":
            self._emit("done_signal", signal=result.done_signal, iteration=iteration)
        else:
            self._emit("no_done_signal", tail=tail)

        success = result.success and promise_state == "DONE"

        if success and self.verifier_adapter is not None and not self.config.use_subagents:
            verifier_result = self._run_verifier(iteration, log_file)
            if verifier_result.promise_state != "PASS":
                success = False
                verifier_tail = "\n".join(
                    verifier_result.stdout.splitlines()[-self.config.tail_lines :]
                )
                tail = f"{tail}\nVerifier: {verifier_tail}".strip()
                promise_state = "VERIFY_FAIL"
                promise_payload = verifier_result.promise_payload or verifier_tail
                self._emit(
                    "verification_failed",
                    iteration=iteration,
                    tail=verifier_tail,
                )
            else:
                self._emit("verification_passed", iteration=iteration)

        for learning in extract_learnings(result.stdout):
            try:
                append_learning(self.cwd, learning)
                self._emit("learning_recorded", learning=learning)
            except Exception:
                pass

        return IterationResult(
            iteration=iteration,
            success=success,
            done_signal=result.done_signal,
            returncode=result.returncode,
            timed_out=result.timed_out,
            log_file=log_file,
            tokens_used=result.tokens_used,
            summary=tail,
            promise_state=promise_state,
            promise_payload=promise_payload,
            stdout=result.stdout,
        )

    def _run_verifier(self, iteration: int, log_file: Path) -> Any:
        """Spawn an independent verifier agent to check the work."""
        self._emit("verification_start", iteration=iteration)

        def _on_line(line: str) -> None:
            with log_file.open("a", encoding="utf-8") as log_f:
                log_f.write(line + "\n")
            self._log_line(line)
            self._emit("output_line", line=line)

        result = self.verifier_adapter.run(  # type: ignore[union-attr]
            VERIFIER_PROMPT, cwd=self.cwd, on_line=_on_line
        )
        self.tokens_used += result.tokens_used
        return result

    def run(self) -> RunSummary:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.main_repo_dir = self._resolve_main_repo_dir()
        self.session_log = self.log_dir / f"owloop_build_session_{_file_timestamp()}.log"

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

        self._init_session()

        if not self.setup_worktree():
            return RunSummary(
                iterations=0,
                branch=self._current_branch(),
                cwd=self.cwd,
                main_repo_dir=self.main_repo_dir,
                stopped_reason="dirty_workspace_declined",
                session_id=self.session_id or "",
                resumed_from_session=self.resumed_from_session,
            )

        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.session_log = self.log_dir / f"owloop_build_session_{_file_timestamp()}.log"

        self._write_prompt_file()

        branch = self._current_branch()
        status = self._spec_status()

        self._emit(
            "session_info",
            model=self.adapter.name,
            branch=branch,
            cwd=str(self.cwd),
            main_repo_dir=str(self.main_repo_dir),
            session_log=str(self.session_log),
            max_iterations=self.config.max_iterations,
            max_tokens=self.config.max_tokens,
            **status,
        )

        if status["has_specs"] and status["incomplete_count"] == 0:
            self._emit("all_specs_complete", spec_count=status["spec_count"])
            return RunSummary(
                iterations=0,
                branch=branch,
                cwd=self.cwd,
                main_repo_dir=self.main_repo_dir,
                stopped_reason="all_specs_complete",
                session_id=self.session_id or "",
                resumed_from_session=self.resumed_from_session,
            )

        inhibitor = SleepInhibitor(emit=lambda kind, data: self._emit(kind, **data))
        inhibitor.start()

        iteration = self._resumed_iterations
        consecutive_failures = 0
        backoff_level = 0
        stopped_reason = "max_iterations"
        blocker: str | None = None
        decision_question: str | None = None
        start_time = time.monotonic() - self._resumed_elapsed_seconds
        self._run_start_time = start_time

        try:
            while True:
                if self.config.max_iterations > 0 and iteration >= self.config.max_iterations:
                    break

                if self.config.max_duration_minutes > 0:
                    elapsed_min = (time.monotonic() - start_time) / 60
                    if elapsed_min >= self.config.max_duration_minutes:
                        stopped_reason = "max_duration"
                        self._emit("max_duration_reached", minutes=int(elapsed_min))
                        break

                if self.config.max_tokens > 0 and self.tokens_used >= self.config.max_tokens:
                    stopped_reason = "max_tokens"
                    self._emit("max_tokens_reached", tokens=self.tokens_used, limit=self.config.max_tokens)
                    break

                iteration += 1
                result = self.run_iteration(iteration)

                # Cross-iteration notes: summarize what just happened.
                note_summary = result.summary
                if result.success:
                    commit_result = self._run_git("log", "-1", "--pretty=%s")
                    if commit_result.returncode == 0 and commit_result.stdout.strip():
                        note_summary = commit_result.stdout.strip()
                self._append_run_note(iteration, result.success, note_summary)

                if result.promise_state == "DONE":
                    consecutive_failures = 0
                    backoff_level = 0
                    if self._check_fix_loop():
                        stopped_reason = "fix_loop_blocked"
                        blocker = "same files modified repeatedly; spec needs to be split"
                        break
                elif result.promise_state == "BLOCKED":
                    stopped_reason = "blocked"
                    blocker = result.promise_payload
                    self._emit("blocked", payload=result.promise_payload)
                    break
                elif result.promise_state == "DECIDE":
                    stopped_reason = "decide"
                    decision_question = result.promise_payload
                    self._emit("decide", payload=result.promise_payload)
                    break
                else:
                    consecutive_failures += 1
                    if consecutive_failures >= self.config.max_consecutive_failures:
                        self._emit("stuck_warning", consecutive_failures=consecutive_failures)
                        backoff_level += 1
                        consecutive_failures = self.config.max_consecutive_failures

                self._push(branch)
                spec_status = self._spec_status()
                self._emit(
                    "iteration_end",
                    iteration=iteration,
                    success=result.success,
                    specs=spec_status["specs"],
                )
                self._persist_session_progress(
                    status="running",
                    iterations=iteration,
                    current_spec=spec_status["first_incomplete"],
                )
                delay = min(
                    self.config.base_retry_delay * (2**backoff_level),
                    self.config.max_retry_delay,
                )
                time.sleep(delay)
        except KeyboardInterrupt:
            stopped_reason = "interrupted"
            self._emit("interrupted", iteration=iteration)
        finally:
            inhibitor.stop()

        self._persist_session_progress(
            status="interrupted" if stopped_reason == "interrupted" else "completed",
            iterations=iteration,
            current_spec=self._spec_status()["first_incomplete"],
        )

        summary = RunSummary(
            iterations=iteration,
            branch=branch,
            cwd=self.cwd,
            main_repo_dir=self.main_repo_dir,
            stopped_reason=stopped_reason,
            tokens_used=self.tokens_used,
            blocker=blocker,
            decision_question=decision_question,
            session_id=self.session_id or "",
            resumed_from_session=self.resumed_from_session,
        )
        self._write_summary(summary)
        return summary

    def _write_summary(self, summary: RunSummary) -> None:
        """Persist the latest run summary so `owloop report` can read it."""
        summary_path = self.log_dir / "owloop_summary_latest.json"
        with summary_path.open("w", encoding="utf-8") as f:
            json.dump(summary.as_dict(), f, indent=2)
