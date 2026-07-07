"""Python port of scripts/owloop.sh — the autonomous build loop engine.

The engine spawns one fresh agent iteration (via an `AgentAdapter`) per round
and watches its output for the ``<promise>DONE</promise>`` completion signal.
Completion is not taken on trust: when the agent claims DONE, the engine itself
runs the spec's acceptance-criteria and backpressure commands via ``subprocess``
(the deterministic verification gate) and only then — never the agent — commits,
pushes, and marks the spec ``COMPLETE``. A failed iteration is rolled back to the
last good commit, and a failure spiral stops the run with a named terminal state
(``stalled``/``exhausted``) rather than retrying forever.

All UI concerns (TUI, plain console) live outside this module: the engine
only reports progress through the ``on_event(kind, data)`` callback so it can
be driven headless (tests, CI) or rendered any way the caller likes. Talking
to the underlying coding agent goes through `AgentAdapter` (see adapters.py)
so the engine itself never shells out to `claude` directly.
"""

from __future__ import annotations

import contextlib
import json
import re
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from owloop import notifications, spec_queue, verification
from owloop.adapters import DEFAULT_IDLE_TIMEOUT, AgentAdapter, AgentResult
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
from owloop.tokens import IterationTokenLimitExceededError, TokenTracker

BUILD_PROMPT = """\
# Owloop — Build Mode

You are running inside an Owloop autonomous loop.

Read these files if they exist (in order):
1. `AGENTS.md` — agent instructions for this project
2. `CLAUDE.md` — coding conventions, architecture rules, tool commands

If a `## Target Spec` section appears above, that is your work item — the
loop's dependency- and priority-aware scheduler already selected it, so do not
scan specs/ for a different one. Only when no Target Spec section is present,
find the highest-priority incomplete work item in specs/ yourself.

Implement the work item completely. Run the shell commands in that spec's
`## Acceptance Criteria` section yourself to check your work as you go. When
everything is implemented and those criteria pass, output `<promise>DONE</promise>`.

The loop — not you — owns git and completion:
- Do NOT commit or push. The loop commits and pushes only after it has
  re-run the acceptance criteria itself and they pass.
- Do NOT add a `Status: COMPLETE` line to the spec. The loop marks the spec
  complete once it has verified the work.
- Do NOT edit the spec's `## Acceptance Criteria` or `## Verification`
  sections, or `.owloop/backpressure.json`. Rewriting your own success
  conditions fails the iteration.

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
"""


class TerminalState(str, Enum):
    """Named terminal states for a run (loop-engineering taxonomy).

    The engine keeps a granular ``stopped_reason`` for diagnostics;
    ``terminal_state`` is the coarse, decision-relevant category reporters and
    exit codes key off. ``EXHAUSTED`` (hit an iteration/duration/token budget)
    must never be presented as ``SUCCESS`` — a run that ran out of budget did
    not finish its work.

    Subclassing ``str`` keeps members JSON-serializable and ``==``-comparable
    to their plain-string values, so callers and persisted summaries can treat
    them as strings without conversion.
    """

    SUCCESS = "success"
    CLEAN_NO_OP = "clean_no_op"
    BLOCKED = "blocked"
    DECIDE = "decide"
    STALLED = "stalled"
    EXHAUSTED = "exhausted"
    TAMPERED = "tampered"
    INTERRUPTED = "interrupted"
    FAILED = "failed"
    SOFT_FAILURE = "soft_failure"

    def __str__(self) -> str:  # so f-strings / json render the value, not "TerminalState.SUCCESS"
        return self.value


class StopReason(str, Enum):
    """Granular reasons the loop stopped, each mapping to a ``TerminalState``.

    These are the exact strings written to ``RunSummary.stopped_reason`` and
    surfaced to the user; the enum keeps them from drifting apart across the
    engine, reporter, TUI, and report generator.
    """

    ALL_SPECS_COMPLETE = "all_specs_complete"
    SUCCESS = "success"
    DRY_RUN_COMPLETE = "dry_run_complete"
    BLOCKED = "blocked"
    DECIDE = "decide"
    STALLED = "stalled"
    FIX_LOOP_BLOCKED = "fix_loop_blocked"
    TAMPERED = "tampered"
    MAX_ITERATIONS = "max_iterations"
    MAX_DURATION = "max_duration"
    MAX_TOKENS = "max_tokens"
    INTERRUPTED = "interrupted"
    PREFLIGHT_FAILED = "preflight_failed"
    DIRTY_WORKSPACE_DECLINED = "dirty_workspace_declined"
    SOFT_FAILURE = "soft_failure"

    def __str__(self) -> str:
        return self.value


class FailureReason(str, Enum):
    """Why a single iteration failed — drives rollback and stall bucketing.

    The exit-code distinction (``CRASH``/``TIMEOUT`` vs ``VERIFICATION_FAILED``)
    lets same-error detection bucket a persistent crash separately from a
    persistent test failure.
    """

    TAMPERED = "tampered"
    TIMEOUT = "timeout"
    EXHAUSTED_ITERATION = "exhausted_iteration"
    CRASH = "crash"
    VERIFICATION_FAILED = "verification_failed"
    NO_DONE_SIGNAL = "no_done_signal"

    def __str__(self) -> str:
        return self.value


_STOPPED_REASON_TO_STATE = {
    StopReason.ALL_SPECS_COMPLETE: TerminalState.SUCCESS,
    StopReason.SUCCESS: TerminalState.SUCCESS,
    StopReason.DRY_RUN_COMPLETE: TerminalState.CLEAN_NO_OP,
    StopReason.BLOCKED: TerminalState.BLOCKED,
    StopReason.DECIDE: TerminalState.DECIDE,
    StopReason.STALLED: TerminalState.STALLED,
    StopReason.FIX_LOOP_BLOCKED: TerminalState.STALLED,
    StopReason.TAMPERED: TerminalState.TAMPERED,
    StopReason.MAX_ITERATIONS: TerminalState.EXHAUSTED,
    StopReason.MAX_DURATION: TerminalState.EXHAUSTED,
    StopReason.MAX_TOKENS: TerminalState.EXHAUSTED,
    StopReason.INTERRUPTED: TerminalState.INTERRUPTED,
    StopReason.PREFLIGHT_FAILED: TerminalState.FAILED,
    StopReason.DIRTY_WORKSPACE_DECLINED: TerminalState.FAILED,
    StopReason.SOFT_FAILURE: TerminalState.SOFT_FAILURE,
}


def classify_terminal_state(stopped_reason: str) -> TerminalState:
    """Map a granular ``stopped_reason`` onto a named terminal state."""
    try:
        reason = StopReason(stopped_reason)
    except ValueError:
        return TerminalState.FAILED
    return _STOPPED_REASON_TO_STATE.get(reason, TerminalState.FAILED)


_ERROR_HASH_RE = re.compile(r"\d+")


def _normalize_error_tail(text: str) -> str:
    """Normalize a failure tail so trivially-varying runs hash the same.

    Strips line numbers, addresses, and timestamps (all digits) and
    whitespace so "the same error" is detected across iterations even when
    only volatile numbers differ.
    """
    return _ERROR_HASH_RE.sub("#", " ".join(text.split())).strip()

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

CONVERGE_PROMPT = """\
# Owloop — Convergence Sweep

Every spec in `.owloop/specs/` is now marked COMPLETE. Your job is to audit
whether the codebase actually satisfies the *collective intent* of those specs,
or whether real work was missed. "Task list empty" does not prove "goal met".

1. Read `AGENTS.md` / `CLAUDE.md` if present, then read every spec in
   `.owloop/specs/` to reconstruct the overall goal.
2. Scan the codebase (Glob/Grep/Read) and run the specs' verification commands
   to check the goal actually holds end-to-end — look for gaps: requirements no
   spec covered, follow-on work implied but never specced, integration seams
   left unwired, missing tests for shipped behavior.

If the goal is fully met with no gaps, output `<promise>DONE</promise>` and
write nothing.

If you find real gaps, create ONE new gap spec per gap as a NEW file in
`.owloop/specs/` using the next available NN- numeric prefix, following the
exact spec template (Priority, Requirements, shell-verifiable Acceptance
Criteria in backticks, Exclusions, Style, Verification). Do NOT edit or
re-open existing COMPLETE specs. Do NOT implement the fixes now — only write
the gap spec(s). Then output `<promise>DONE</promise>`.
"""

EventCallback = Callable[[str, dict], None]

# Newest run-note entries carried into each iteration prompt. run-notes.md
# gains an entry per iteration; shipping the whole file makes long runs
# progressively slower (more input tokens per round) and buries the current
# task under stale history. The full file stays on disk.
MAX_RUN_NOTE_ENTRIES = 5

_RUN_NOTE_ENTRY_RE = re.compile(r"(?m)^(?=## Iteration )")


def trim_run_notes(notes: str, max_entries: int = MAX_RUN_NOTE_ENTRIES) -> str:
    """Keep only the newest ``max_entries`` run-note entries for the prompt.

    Content without ``## Iteration`` headers (legacy or hand-written notes)
    is returned unchanged.
    """
    entries = [e for e in _RUN_NOTE_ENTRY_RE.split(notes) if e.strip()]
    dated = [e for e in entries if e.startswith("## Iteration ")]
    if len(dated) <= max_entries:
        return notes
    omitted = len(dated) - max_entries
    kept = "".join(dated[-max_entries:]).strip()
    return (
        f"({omitted} older iteration notes omitted — full history in run-notes.md)\n\n"
        f"{kept}"
    )


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
    max_tokens_per_iteration: int = 0  # 0 = unlimited
    idle_timeout: float = DEFAULT_IDLE_TIMEOUT  # seconds, passed to adapter
    worktree: bool = True
    max_consecutive_failures: int = 3
    max_same_error_count: int = 5
    # When True, keep the legacy behavior: warn + back off on repeated
    # failures and retry forever. When False (default), a failure spiral is a
    # first-class terminal state (``stalled``) and the loop hard-stops.
    keep_retrying: bool = False
    # Reset the worktree to the last good commit after a failed iteration so
    # the next "fresh context" round starts clean. Opt out with --no-rollback.
    rollback: bool = True
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
    # When True, run exactly one iteration, skip push, revert any commit the
    # iteration made, and produce a DryRunReport instead of looping.
    dry_run: bool = False
    # When True, commit and mark specs complete locally but never push. Useful
    # for review-before-push workflows or CI dry runs that want real commits.
    no_push: bool = False
    # Completion notifications: fire a webhook and/or desktop notification when
    # the run stops on an attention-worthy terminal state. None/False = off.
    notify_webhook: str | None = None
    notify_desktop: bool = False
    # Post-queue convergence sweep (#36): after all specs complete, run up to
    # this many audit passes that append gap specs; 0 = disabled.
    converge_sweeps: int = 0


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
    limit_reached: bool = False
    crashed: bool = False


@dataclass
class DryRunReport:
    """Concise pass/fail report produced by a ``--dry-run`` / ``--one-shot`` run."""

    promise_done: bool
    acceptance_passed: int
    acceptance_failed: int
    tokens_used: int
    spec_name: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "promise_done": self.promise_done,
            "acceptance_passed": self.acceptance_passed,
            "acceptance_failed": self.acceptance_failed,
            "tokens_used": self.tokens_used,
            "spec_name": self.spec_name,
        }


@dataclass
class RunSummary:
    iterations: int
    branch: str
    cwd: Path
    main_repo_dir: Path
    stopped_reason: str
    terminal_state: str = ""
    issues: list[str] | None = None
    tokens_used: int = 0
    estimated_cost_usd: float = 0.0
    blocker: str | None = None
    decision_question: str | None = None
    session_id: str = ""
    resumed_from_session: str | None = None
    dry_run_report: DryRunReport | None = None

    @property
    def state(self) -> str:
        """Named terminal state for this run (see ``TerminalState``)."""
        return self.terminal_state or classify_terminal_state(self.stopped_reason)

    @property
    def is_success(self) -> bool:
        return self.state == TerminalState.SUCCESS

    @property
    def is_exhausted(self) -> bool:
        """True when the run stopped because it ran out of budget, not work."""
        return self.state == TerminalState.EXHAUSTED

    def as_dict(self) -> dict[str, Any]:
        return {
            "iterations": self.iterations,
            "branch": self.branch,
            "cwd": str(self.cwd),
            "main_repo_dir": str(self.main_repo_dir),
            "stopped_reason": self.stopped_reason,
            "terminal_state": self.terminal_state or classify_terminal_state(self.stopped_reason),
            "issues": self.issues,
            "tokens_used": self.tokens_used,
            "estimated_cost_usd": self.estimated_cost_usd,
            "blocker": self.blocker,
            "decision_question": self.decision_question,
            "session_id": self.session_id,
            "resumed_from_session": self.resumed_from_session,
            "dry_run_report": self.dry_run_report.as_dict() if self.dry_run_report else None,
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
        self.estimated_cost_usd = 0.0
        self.session_id = config.session_id
        self.resumed_from_session: str | None = None
        self._resumed_iterations = 0
        self._resumed_elapsed_seconds = 0.0
        self._run_start_time: float | None = None
        # Append-mode file handles kept open across writes. The event log and
        # session log receive one line per agent output line; reopening the
        # file for each of those writes is measurable overhead on chatty
        # iterations. Keyed by path because both logs can move when the run
        # enters a worktree.
        self._append_handles: dict[Path, Any] = {}

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

    def _append_line_to(self, path: Path, text: str) -> None:
        """Append one line via a cached open handle, flushed per write."""
        handle = self._append_handles.get(path)
        if handle is None or handle.closed:
            path.parent.mkdir(parents=True, exist_ok=True)
            handle = path.open("a", encoding="utf-8")
            self._append_handles[path] = handle
        handle.write(text + "\n")
        handle.flush()

    def _log_event(self, kind: str, data: dict[str, Any]) -> None:
        """Append one JSON line for this event; creates the log lazily."""
        record = {
            "ts": datetime.now().isoformat(),
            "session_id": self.session_id,
            "kind": kind,
            "data": data,
        }
        self._append_line_to(self._events_log_path(), json.dumps(record, default=str))

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
            self._append_line_to(self.session_log, text)

    def _is_git_repo(self) -> bool:
        return self._run_git("rev-parse", "--is-inside-work-tree").returncode == 0

    _OWLOOP_OWNED_PREFIXES = (".owloop",)

    def _is_path_owned(self, path: str) -> bool:
        """Return True if a path belongs to owloop's own state directories."""
        for prefix in self._OWLOOP_OWNED_PREFIXES:
            if path == prefix or path.startswith(prefix + "/"):
                return True
        return False

    def _is_dirty(self) -> bool:
        result = self._run_git("status", "--porcelain")
        for line in result.stdout.splitlines():
            # Porcelain format: "XY path" or "XY orig -> dest".
            path_part = line[3:].strip()
            # If this is a rename, check both sides.
            if " -> " in path_part:
                source, _, dest = path_part.partition(" -> ")
                if self._is_path_owned(source) and self._is_path_owned(dest):
                    continue
            elif self._is_path_owned(path_part):
                continue
            return True
        return False

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

    def _copy_dot_dir(
        self, worktree_path: Path, name: str, event_name: str, skip: tuple[str, ...] = ()
    ) -> None:
        """Copy a dot-directory from the main repo into a new worktree.

        Git does not track ``.owloop/`` or ``.claude/`` by default, so the
        worktree needs its own copies for prompts, specs, and agent settings.
        If the target already exists (e.g., a tracked ``.owloop/specs/`` was
        materialized by ``git worktree add``), we still need to sync the latest
        contents from the main repo so new/untracked specs and prompts show up.
        ``skip`` names top-level entries to leave out of the copy.
        """
        source = self.main_repo_dir / name
        target = worktree_path / name
        if not source.is_dir():
            return
        ignore = shutil.ignore_patterns(*skip) if skip else None
        if target.exists():
            shutil.copytree(source, target, dirs_exist_ok=True, ignore=ignore)
            self._emit(f"{event_name}_synced", path=str(target))
        else:
            shutil.copytree(source, target, ignore=ignore)
            self._emit(event_name, path=str(target))

    def _copy_claude_config(self, worktree_path: Path) -> None:
        """Copy agent config directories into a new worktree.

        ``.claude/`` is always copied (project-level permissions/settings);
        adapters may declare additional per-tool directories via a
        ``config_dirs`` attribute (e.g. ``.qoder/`` for the Qoder preset).
        """
        self._copy_dot_dir(worktree_path, ".claude", "claude_config_copied")
        extra = getattr(self.adapter, "config_dirs", ()) or ()
        for name in extra:
            if name != ".claude":
                self._copy_dot_dir(worktree_path, name, "agent_config_copied")

    def _copy_owloop_dir(self, worktree_path: Path) -> None:
        """Copy the main repo's .owloop/ into a new worktree.

        This keeps specs and prompt files in the worktree so the loop can read
        and write them without touching the original checkout. ``logs/`` is
        deliberately not copied: after long runs it is by far the largest part
        of ``.owloop/`` (per-iteration logs, ``events.jsonl``), the worktree
        writes its own logs anyway, and stale main-repo logs would only shadow
        them.
        """
        self._copy_dot_dir(worktree_path, ".owloop", "owloop_dir_copied", skip=("logs",))

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

    @staticmethod
    def _slugify(text: str) -> str:
        """Turn arbitrary text into a git-safe branch slug."""
        slug = text.lower()
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        slug = slug.strip("-")
        slug = re.sub(r"-+", "-", slug)
        return slug[:40]

    _MAX_SLUG_LEN = 40

    def _spec_slug(self) -> str:
        """Derive a short slug from the active spec or fall back to 'run'."""
        spec = spec_queue.get_next_ready_spec(self.specs_dir)
        if spec is None:
            return "run"
        # Strip leading numeric prefix (e.g. "01-extract-issue-service").
        stem = re.sub(r"^\d+-", "", spec.stem)
        slug = self._slugify(stem)
        return slug or "run"

    @staticmethod
    def _session_id_from_branch(branch: str) -> str:
        """Extract the trailing session id from an owloop branch name.

        Supports both legacy ``owloop/<date>-<session_id>`` and sluggified
        ``owloop/<date>-<slug>-<session_id>`` formats.
        """
        rest = branch.split("/", 1)[1]
        # The session id is the last '-'-delimited token.
        return rest.rsplit("-", 1)[-1]

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
                # Branch format: owloop/<date>-<slug>-<session_id>
                session_id = self._session_id_from_branch(branch)
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
        slug = self._spec_slug()
        branch = f"owloop/{wt_date}-{slug}-{session_id}"
        wt_path = wt_base / f"owloop-{wt_date}-{slug}-{session_id}"

        # Guard against an extremely unlikely collision.
        while self._branch_exists(branch):
            session_id = uuid.uuid4().hex[:8]
            branch = f"owloop/{wt_date}-{slug}-{session_id}"
            wt_path = wt_base / f"owloop-{wt_date}-{slug}-{session_id}"

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

    def _run_notes_path(self) -> Path:
        """Loop metadata lives under ``.owloop/`` so it can never leak into
        a commit the engine makes with ``git add -A``."""
        return resolve_owloop_dir(self.cwd) / "run-notes.md"

    def _read_run_notes(self) -> str | None:
        path = self._run_notes_path()
        if path.is_file():
            return path.read_text(encoding="utf-8")
        # Back-compat: earlier versions wrote run-notes.md to the repo root.
        legacy = self.cwd / "run-notes.md"
        if legacy.is_file():
            return legacy.read_text(encoding="utf-8")
        return None

    def _read_steering(self) -> str | None:
        path = self.cwd / "STEERING.md"
        if path.is_file():
            return path.read_text(encoding="utf-8")
        return None

    def _target_spec_section(self, spec_name: str | None) -> str | None:
        """Inline the engine-selected spec so the agent skips re-discovery.

        Without this, every fresh-context iteration spends its opening minutes
        (and tool calls) re-deriving what ``spec_queue.get_next_ready_spec``
        already computed — and, not knowing the Priority/Depends-On
        conventions, can land on a different spec than the engine will verify.
        """
        if not spec_name:
            return None
        spec_path = self.specs_dir / spec_name
        try:
            content = spec_path.read_text(encoding="utf-8")
        except OSError:
            return None
        self._emit("target_spec_selected", spec=spec_name)
        return (
            "## Target Spec\n\n"
            f"The loop has selected your work item: `{spec_name}` "
            f"(on disk at `{spec_path}`). Implement this spec — do not pick a "
            "different one. Its current content follows:\n\n"
            f"{content.strip()}"
        )

    def _build_prompt_with_context(
        self, prompt_text: str, target_spec: str | None = None
    ) -> str:
        """Prepend run-notes, STEERING.md, learnings, and the target spec."""
        sections: list[str] = []

        steering = self._read_steering()
        if steering is not None:
            self._emit("steering_loaded", path=str(self.cwd / "STEERING.md"))
            sections.append(
                "The user has provided mid-flight guidance in STEERING.md. "
                "Follow these instructions for this iteration.\n\n"
                f"{steering}"
            )

        failure_feedback = self._read_failure_feedback()
        if failure_feedback is not None:
            self._emit("failure_feedback_loaded", path=str(self._failure_feedback_path()))
            sections.append(
                "The previous iteration FAILED verification and was rolled back. "
                "Start from the diagnosis below instead of rediscovering it, and "
                "fix the root cause rather than repeating the same approach.\n\n"
                f"{failure_feedback}"
            )

        notes = self._read_run_notes()
        if notes is not None:
            self._emit("run_notes_loaded", path=str(self._run_notes_path()))
            sections.append(
                "The following notes were recorded during previous iterations of this run. "
                "Read them to avoid repeating mistakes.\n\n"
                f"{trim_run_notes(notes)}"
            )

        learnings_text = format_learnings_for_prompt(load_learnings(self.cwd))
        if learnings_text:
            self._emit("learnings_loaded", path=str(self.cwd / ".owloop" / "learnings.md"))
            sections.append(learnings_text)

        spec_section = self._target_spec_section(target_spec)
        if spec_section is not None:
            sections.append(spec_section)

        if not sections:
            return prompt_text

        context = "\n\n---\n\n".join(sections)
        return f"{context}\n\n---\n\n{prompt_text}"

    def _append_run_note(
        self, iteration: int, success: bool, summary: str, learning: str = ""
    ) -> None:
        """Append a concise cross-iteration note to run-notes.md."""
        run_notes_path = self._run_notes_path()
        run_notes_path.parent.mkdir(parents=True, exist_ok=True)
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



    def _guarded_hash(self, spec_name: str | None) -> str:
        """Hash the spec sections + backpressure file the agent must not edit."""
        return verification.guarded_hash(self.cwd, self.specs_dir, spec_name)

    def _run_verification_gate(
        self, iteration: int, spec_name: str | None, guard_before: str
    ) -> verification.GateResult:
        """Deterministically verify an iteration outside the agent's control.

        Delegates to the shared gate in ``verification.py`` (the single
        definition of "verified" used by both the sequential engine and the
        parallel orchestrator) and emits the gate events. ``failures`` carries
        per-command details for the next iteration's failure feedback. A
        tampered guard region fails the iteration with a distinct
        ``spec_tampered`` event.
        """
        self._emit("verification_gate_start", iteration=iteration, spec=spec_name)
        result = verification.run_gate(self.cwd, self.specs_dir, spec_name, guard_before)

        if result.tampered:
            self._emit("spec_tampered", iteration=iteration, spec=spec_name)
            return verification.GateResult(passed=False, tampered=True, passed_count=0, failed_count=0)

        if result.passed:
            self._emit(
                "verification_gate_passed",
                iteration=iteration,
                passed=result.passed_count,
            )
        elif result.soft_failure:
            self._emit(
                "verification_gate_soft_failure",
                iteration=iteration,
                passed=result.passed_count,
                failed=result.failed_count,
                commands=[f["command"] for f in result.failures],
            )
        else:
            self._emit(
                "verification_gate_failed",
                iteration=iteration,
                passed=result.passed_count,
                failed=result.failed_count,
                commands=[f["command"] for f in result.failures],
            )
        return result

    def _head(self) -> str:
        return str(self._run_git("rev-parse", "HEAD").stdout).strip()

    def _commit_iteration(self, iteration: int, spec_name: str | None) -> bool:
        """Stage and commit the verified work. Engine-owned, gate-gated.

        Loop metadata (``.owloop/run-notes.md``) is unstaged before commit so
        it can never enter project history even on repos that predate the
        ``.gitignore`` entry.
        """
        self._run_git("add", "-A")
        self._run_git(
            "reset", "--quiet", "--",
            ".owloop/run-notes.md", ".owloop/logs", ".owloop/PROMPT_build.md",
            ".owloop/last-failure.md",
        )
        subject = f"owloop: complete {spec_name}" if spec_name else f"owloop: iteration {iteration}"
        committed = self._run_git("commit", "-m", subject)
        if committed.returncode == 0:
            self._emit("iteration_committed", iteration=iteration, spec=spec_name, subject=subject)
            return True
        # Nothing to commit (e.g. work already on disk) is not an error.
        self._emit("iteration_commit_noop", iteration=iteration, spec=spec_name)
        return False

    def _mark_spec_complete(self, spec_name: str | None) -> None:
        """Flip the active spec to COMPLETE — only the engine does this."""
        if not spec_name:
            return
        if spec_queue.mark_spec_complete(self.specs_dir / spec_name):
            self._emit("spec_marked_complete", spec=spec_name)

    def _rollback_iteration(self, iteration: int, last_good: str) -> None:
        """Reset the worktree to the last good commit after a failed iteration.

        Failures are data: the discarded diff is saved as a patch under
        ``.owloop/logs/`` before the tree is reset, so nothing is lost. The
        reset restores the disk-state invariant owloop's "fresh context per
        iteration" design depends on — the next round starts from a known
        commit instead of on top of half-finished edits.
        """
        if not self.config.rollback:
            self._emit("rollback_skipped", iteration=iteration, reason="disabled")
            return
        if not self._is_git_repo() or not last_good:
            return

        # Intent-to-add untracked files (excluding loop metadata) so the saved
        # patch captures them too. .owloop/ is excluded from the add so the
        # follow-up `reset --hard` can't delete PROMPT_build.md/specs/logs.
        self._run_git("add", "-A", "-N", "--", ".", ":!.owloop")
        diff = self._run_git("diff", last_good, "--", ".", ":!.owloop")
        patch_path = self.log_dir / f"iter_{iteration}_discarded.patch"
        if diff.stdout.strip():
            self.log_dir.mkdir(parents=True, exist_ok=True)
            patch_path.write_text(diff.stdout, encoding="utf-8")

        self._run_git("reset", "--hard", last_good)
        # Remove untracked files the agent created, but never touch loop
        # metadata (specs, logs, learnings, run-notes) under .owloop/.
        self._run_git("clean", "-fd", "-e", ".owloop")
        self._emit(
            "iteration_rolled_back",
            iteration=iteration,
            to_commit=last_good[:8],
            patch=str(patch_path) if diff.stdout.strip() else None,
        )

    def run_iteration(self, iteration: int, target_spec: str | None = None) -> IterationResult:
        owloop_dir = resolve_owloop_dir(self.cwd)
        prompt_file = owloop_dir / "PROMPT_build.md"
        log_file = self.log_dir / (
            f"owloop_build_iter_{iteration}_{_file_timestamp()}.log"
        )

        self._emit("iteration_start", iteration=iteration, timestamp=_timestamp())

        prompt_text = self._build_prompt_with_context(
            prompt_file.read_text(encoding="utf-8"), target_spec=target_spec
        )

        cap_tracker = TokenTracker()
        iteration_tokens = 0

        with log_file.open("w", encoding="utf-8") as log_f:

            def _on_line(line: str) -> None:
                nonlocal iteration_tokens
                log_f.write(line + "\n")
                self._log_line(line)
                self._emit("output_line", line=line)
                if self.config.max_tokens_per_iteration > 0:
                    iteration_tokens += cap_tracker.count_from_line(line)
                    if iteration_tokens > self.config.max_tokens_per_iteration:
                        raise IterationTokenLimitExceededError(iteration_tokens)

            try:
                if self.config.use_subagents:
                    orchestrator = SubagentOrchestrator(
                        self.adapter, self.verifier_adapter, self.cwd, on_line=_on_line
                    )
                    result = orchestrator.run()
                else:
                    result = self.adapter.run(prompt_text, cwd=self.cwd, on_line=_on_line)
            except IterationTokenLimitExceededError as exc:
                self._emit(
                    "iteration_token_limit_exceeded",
                    iteration=iteration,
                    tokens=exc.tokens_used,
                    limit=self.config.max_tokens_per_iteration,
                )
                result = AgentResult(
                    stdout="",
                    returncode=-1,
                    success=False,
                    has_completion_signal=False,
                    tokens_used=exc.tokens_used,
                    limit_reached=True,
                )

        tail = "\n".join(result.stdout.splitlines()[-self.config.tail_lines :])
        parsed = parse_promise_signal(result.stdout)
        promise_state = parsed[0] if parsed else ""
        promise_payload = parsed[1] if parsed else ""

        self.tokens_used += result.tokens_used
        self.estimated_cost_usd += result.cost_usd
        self._emit(
            "tokens_update",
            iteration=iteration,
            tokens_used=result.tokens_used,
            total_tokens=self.tokens_used,
            cost_usd=result.cost_usd,
            total_cost_usd=self.estimated_cost_usd,
        )

        limit_reached = getattr(result, "limit_reached", False)
        crashed = (not result.timed_out) and result.returncode != 0 and not limit_reached

        if result.timed_out:
            self._emit("agent_timeout", iteration=iteration)
        elif limit_reached:
            self._emit(
                "iteration_exhausted", iteration=iteration, tokens=result.tokens_used
            )
        elif not result.success:
            self._emit("agent_failed", returncode=result.returncode, tail=tail)
        elif promise_state == "DONE":
            self._emit("done_signal", signal=result.done_signal, iteration=iteration)
        else:
            self._emit("no_done_signal", tail=tail)

        success = result.success and promise_state == "DONE"

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
            limit_reached=limit_reached,
            crashed=crashed,
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
        self.estimated_cost_usd += result.cost_usd
        return result

    def _run_converge_sweep(self, sweep: int) -> bool:
        """Audit the completed queue for missed work; append linted gap specs.

        Runs one audit agent pass (#36). Any new spec files it writes are run
        through ``SpecLinter`` before they may enter the queue — invalid gap
        specs are rejected (removed) so a malformed audit can't poison the loop.
        Returns True when at least one valid gap spec was appended (the loop
        should keep going), False when the codebase has converged.
        """
        from owloop.spec_linter import SpecLinter

        self._emit("converge_sweep_start", sweep=sweep)
        before = {p.name for p in spec_queue.get_root_specs(self.specs_dir)}

        result = self.adapter.run(
            CONVERGE_PROMPT,
            cwd=self.cwd,
            on_line=lambda line: self._emit("output_line", line=line),
        )
        self.tokens_used += result.tokens_used
        self.estimated_cost_usd += result.cost_usd

        after = spec_queue.get_root_specs(self.specs_dir)
        new_specs = [p for p in after if p.name not in before]

        linter = SpecLinter(self.specs_dir, project_dir=self.cwd)
        accepted: list[str] = []
        for spec in new_specs:
            errors = [f for f in linter.lint_spec(spec) if f.severity == "error"]
            if errors:
                spec.unlink(missing_ok=True)
                self._emit(
                    "converge_spec_rejected",
                    sweep=sweep,
                    spec=spec.name,
                    errors=[f.message for f in errors],
                )
            else:
                accepted.append(spec.name)

        if accepted:
            self._emit("converge_gap_specs", sweep=sweep, specs=accepted)
            return True
        self._emit("converged", sweep=sweep)
        return False

    def _apply_llm_verifier(self, iteration: int, result: IterationResult) -> bool:
        """Run the independent LLM verifier as a second, orthogonal signal.

        Ordering matters for speed and cost: this model roundtrip only runs on
        work that already survived the deterministic gate (seconds, no tokens),
        so mechanically-broken iterations never pay for it. Returns True on
        PASS; on FAIL mutates ``result`` into a VERIFY_FAIL failure so
        classification and failure feedback see the verifier's verdict.
        """
        verifier_result = self._run_verifier(iteration, result.log_file)
        if verifier_result.promise_state == "PASS":
            self._emit("verification_passed", iteration=iteration)
            return True
        verifier_tail = "\n".join(
            verifier_result.stdout.splitlines()[-self.config.tail_lines :]
        )
        result.success = False
        result.summary = f"{result.summary}\nVerifier: {verifier_tail}".strip()
        result.promise_state = "VERIFY_FAIL"
        result.promise_payload = verifier_result.promise_payload or verifier_tail
        self._emit("verification_failed", iteration=iteration, tail=verifier_tail)
        return False

    def _failure_feedback_path(self) -> Path:
        return resolve_owloop_dir(self.cwd) / "last-failure.md"

    def _write_failure_feedback(
        self,
        iteration: int,
        failure_reason: FailureReason,
        result: IterationResult,
        gate_failures: list[dict[str, Any]],
    ) -> None:
        """Persist why this iteration failed so the next retry starts informed.

        Without this, a fresh-context retry inherits only a five-line stdout
        tail and usually re-diagnoses (or repeats) the same mistake — the most
        expensive way an unattended loop can be slow. The file is injected
        into the next prompt and deleted on the next verified success.
        """
        lines = [
            f"# Previous iteration failed (iteration {iteration})",
            "",
            f"- Failure type: {failure_reason}",
        ]
        if result.promise_state == "VERIFY_FAIL" and result.promise_payload:
            lines.append(f"- Independent verifier verdict: {result.promise_payload}")
        if gate_failures:
            lines += ["", "## Commands that failed verification"]
            for failure in gate_failures:
                lines += [
                    "",
                    f"### `{failure['command']}` (exit {failure['returncode']})",
                    "```",
                    failure["output"] or "(no output)",
                    "```",
                ]
        tail = "\n".join(result.stdout.splitlines()[-30:]).strip()
        if tail:
            lines += ["", "## Agent output tail", "```", tail, "```"]
        path = self._failure_feedback_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self._emit("failure_feedback_written", path=str(path), iteration=iteration)

    def _read_failure_feedback(self) -> str | None:
        path = self._failure_feedback_path()
        if path.is_file():
            return path.read_text(encoding="utf-8")
        return None

    def _clear_failure_feedback(self) -> None:
        with contextlib.suppress(OSError):
            self._failure_feedback_path().unlink(missing_ok=True)

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
                stopped_reason=StopReason.PREFLIGHT_FAILED,
                issues=issues,
            )

        self._init_session()

        if not self.setup_worktree():
            return RunSummary(
                iterations=0,
                branch=self._current_branch(),
                cwd=self.cwd,
                main_repo_dir=self.main_repo_dir,
                stopped_reason=StopReason.DIRTY_WORKSPACE_DECLINED,
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
                stopped_reason=StopReason.ALL_SPECS_COMPLETE,
                session_id=self.session_id or "",
                resumed_from_session=self.resumed_from_session,
            )

        inhibitor = SleepInhibitor(emit=lambda kind, data: self._emit(kind, **data))
        inhibitor.start()

        iteration = self._resumed_iterations
        consecutive_failures = 0
        same_error_counts: dict[str, int] = {}
        converge_sweeps_done = 0
        backoff_level = 0
        stopped_reason = StopReason.MAX_ITERATIONS
        blocker: str | None = None
        decision_question: str | None = None
        dry_run_report: DryRunReport | None = None
        dry_run_original_head = ""
        if self.config.dry_run:
            dry_run_original_head = self._run_git("rev-parse", "HEAD").stdout.strip()
        # A dry run always stops after exactly one iteration, no matter what
        # --max-iterations was passed.
        max_iterations = 1 if self.config.dry_run else self.config.max_iterations
        start_time = time.monotonic() - self._resumed_elapsed_seconds
        self._run_start_time = start_time

        try:
            while True:
                if max_iterations > 0 and iteration >= max_iterations:
                    break

                if self.config.max_duration_minutes > 0:
                    elapsed_min = (time.monotonic() - start_time) / 60
                    if elapsed_min >= self.config.max_duration_minutes:
                        stopped_reason = StopReason.MAX_DURATION
                        self._emit("max_duration_reached", minutes=int(elapsed_min))
                        break

                if self.config.max_tokens > 0 and self.tokens_used >= self.config.max_tokens:
                    stopped_reason = StopReason.MAX_TOKENS
                    self._emit("max_tokens_reached", tokens=self.tokens_used, limit=self.config.max_tokens)
                    break

                active_status = self._spec_status()
                active_spec = active_status["first_incomplete"]
                # Snapshot the guarded regions (acceptance criteria, verification
                # section, backpressure) and the last good commit *before* the
                # agent runs, so tamper detection and rollback have a baseline.
                guard_before = self._guarded_hash(active_spec)
                last_good = self._head()

                iteration += 1
                result = self.run_iteration(iteration, target_spec=active_spec)

                if self.config.dry_run:
                    self._append_run_note(iteration, result.success, result.summary)
                    acceptance_passed, acceptance_failed, _, _, _ = verification.run_acceptance_criteria(
                        self.cwd, self.specs_dir, active_spec
                    )
                    current_head = self._head()
                    if current_head and current_head != dry_run_original_head:
                        self._run_git("reset", "--soft", dry_run_original_head)
                        self._emit(
                            "dry_run_commit_reverted",
                            from_head=current_head,
                            to_head=dry_run_original_head,
                        )
                    dry_run_report = DryRunReport(
                        promise_done=result.promise_state == "DONE",
                        acceptance_passed=acceptance_passed,
                        acceptance_failed=acceptance_failed,
                        tokens_used=result.tokens_used,
                        spec_name=active_spec,
                    )
                    self._emit("dry_run_report", **dry_run_report.as_dict())
                    stopped_reason = StopReason.DRY_RUN_COMPLETE
                    break

                # ── Terminal agent signals stop the loop before verification ──
                if result.promise_state == "BLOCKED":
                    self._append_run_note(iteration, False, result.summary)
                    stopped_reason = StopReason.BLOCKED
                    blocker = result.promise_payload
                    self._emit("blocked", payload=result.promise_payload)
                    break
                if result.promise_state == "DECIDE":
                    self._append_run_note(iteration, False, result.summary)
                    stopped_reason = StopReason.DECIDE
                    decision_question = result.promise_payload
                    self._emit("decide", payload=result.promise_payload)
                    break

                # ── Deterministic verification gate (engine-owned) ──
                gate_result = verification.GateResult(passed=False, tampered=False, passed_count=0, failed_count=0)
                if result.promise_state == "DONE":
                    gate_result = self._run_verification_gate(
                        iteration, active_spec, guard_before
                    )
                    # Shell-first ordering: the expensive LLM verifier runs only
                    # on work that already survived the mechanical gate.
                    if (
                        gate_result.passed
                        and self.verifier_adapter is not None
                        and not self.config.use_subagents
                    ):
                        gate_result = verification.GateResult(
                            passed=self._apply_llm_verifier(iteration, result),
                            tampered=False,
                            passed_count=gate_result.passed_count,
                            failed_count=gate_result.failed_count,
                        )

                if gate_result.passed:
                    # Verified success: only now does the engine commit, mark the
                    # spec complete, and push — never the agent.
                    consecutive_failures = 0
                    backoff_level = 0
                    same_error_counts.clear()
                    self._clear_failure_feedback()
                    # Cross-iteration note: read the commit subject before the
                    # engine makes its own commit below.
                    note_summary = result.summary
                    commit_result = self._run_git("log", "-1", "--pretty=%s")
                    if commit_result.returncode == 0 and commit_result.stdout.strip():
                        note_summary = commit_result.stdout.strip()
                    self._append_run_note(iteration, True, note_summary)
                    self._mark_spec_complete(active_spec)
                    self._commit_iteration(iteration, active_spec)
                    if self.config.no_push:
                        self._emit("push_skipped", branch=branch)
                    else:
                        self._push(branch)
                    spec_status = self._spec_status()
                    self._emit(
                        "iteration_end",
                        iteration=iteration,
                        success=True,
                        specs=spec_status["specs"],
                    )
                    self._persist_session_progress(
                        status="running",
                        iterations=iteration,
                        current_spec=spec_status["first_incomplete"],
                    )
                    if self._check_fix_loop():
                        stopped_reason = StopReason.FIX_LOOP_BLOCKED
                        blocker = "same files modified repeatedly; spec needs to be split"
                        break
                    if spec_status["has_specs"] and spec_status["incomplete_count"] == 0:
                        # Queue empty: optionally audit for missed work before
                        # declaring success (#36). A sweep that appends gap specs
                        # keeps the loop running; convergence (or the sweep cap)
                        # ends it as success.
                        if (
                            not self.config.dry_run
                            and converge_sweeps_done < self.config.converge_sweeps
                        ):
                            converge_sweeps_done += 1
                            if self._run_converge_sweep(converge_sweeps_done):
                                time.sleep(
                                    min(self.config.base_retry_delay, self.config.max_retry_delay)
                                )
                                continue
                        stopped_reason = StopReason.SUCCESS
                        self._emit("all_specs_complete", spec_count=spec_status["spec_count"])
                        break
                    # No delay after a verified success — the next agent
                    # iteration is minutes of work; waiting here buys nothing.
                    continue

                # ── Soft failure: functional checks pass, meta-check fails ──
                if gate_result.soft_failure:
                    self._append_run_note(iteration, False, result.summary)
                    diff = self._run_git("diff", last_good, "--", ".", ":!.owloop")
                    self._emit(
                        "soft_failure",
                        iteration=iteration,
                        spec=active_spec,
                        diff=diff.stdout or "",
                        commands=[f["command"] for f in gate_result.failures],
                    )
                    stopped_reason = StopReason.SOFT_FAILURE
                    break

                # ── Failure: classify, record feedback, roll back, stop on a stall ──
                if gate_result.tampered:
                    failure_reason = FailureReason.TAMPERED
                elif result.timed_out:
                    failure_reason = FailureReason.TIMEOUT
                elif result.limit_reached:
                    failure_reason = FailureReason.EXHAUSTED_ITERATION
                elif result.crashed:
                    failure_reason = FailureReason.CRASH
                elif result.promise_state == "VERIFY_FAIL":
                    failure_reason = FailureReason.VERIFICATION_FAILED
                elif result.promise_state == "DONE":
                    failure_reason = FailureReason.VERIFICATION_FAILED
                    self._emit("verification_failed", iteration=iteration, tail=result.summary)
                else:
                    failure_reason = FailureReason.NO_DONE_SIGNAL

                self._append_run_note(iteration, False, result.summary)
                # Written before rollback; .owloop/ is excluded from the reset,
                # so the next iteration's prompt starts from this diagnosis.
                self._write_failure_feedback(iteration, failure_reason, result, gate_result.failures)
                self._rollback_iteration(iteration, last_good)

                consecutive_failures += 1
                error_key = f"{failure_reason.value}:{_normalize_error_tail(result.summary or '')}"[:500]
                same_error_counts[error_key] = same_error_counts.get(error_key, 0) + 1

                spec_status = self._spec_status()
                self._emit(
                    "iteration_end",
                    iteration=iteration,
                    success=False,
                    specs=spec_status["specs"],
                )
                self._persist_session_progress(
                    status="running",
                    iterations=iteration,
                    current_spec=spec_status["first_incomplete"],
                )

                if not self.config.keep_retrying:
                    if same_error_counts[error_key] >= self.config.max_same_error_count:
                        stopped_reason = StopReason.STALLED
                        self._emit(
                            "stalled",
                            reason="same_error",
                            failures=same_error_counts[error_key],
                            failure_reason=failure_reason.value,
                        )
                        break
                    if consecutive_failures >= self.config.max_consecutive_failures:
                        stopped_reason = StopReason.STALLED
                        self._emit(
                            "stalled",
                            reason="consecutive_failures",
                            failures=consecutive_failures,
                            failure_reason=failure_reason.value,
                        )
                        break
                elif consecutive_failures >= self.config.max_consecutive_failures:
                    # Legacy --keep-retrying mode: warn, back off, never stop.
                    self._emit("stuck_warning", consecutive_failures=consecutive_failures)
                    backoff_level += 1
                    consecutive_failures = self.config.max_consecutive_failures

                delay = min(
                    self.config.base_retry_delay * (2**backoff_level),
                    self.config.max_retry_delay,
                )
                time.sleep(delay)
        except KeyboardInterrupt:
            stopped_reason = StopReason.INTERRUPTED
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
            stopped_reason=str(stopped_reason),
            terminal_state=classify_terminal_state(stopped_reason),
            tokens_used=self.tokens_used,
            estimated_cost_usd=self.estimated_cost_usd,
            blocker=blocker,
            decision_question=decision_question,
            session_id=self.session_id or "",
            resumed_from_session=self.resumed_from_session,
            dry_run_report=dry_run_report,
        )
        self._write_summary(summary)
        self._generate_report()
        self._notify(summary)
        self._close_append_handles()
        return summary

    def _generate_report(self) -> None:
        """Generate a static HTML report inside the worktree (best-effort)."""
        try:
            from owloop.report import ReportGenerator
            from owloop.report_ai import ReportInsights

            report_path = self.cwd / ".owloop" / "reports" / "owloop_report_latest.html"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            generator = ReportGenerator(self.cwd)
            generator.generate(
                output_path=report_path,
                insights=ReportInsights(),
                use_tailwind=False,
            )
        except Exception:
            # Report generation must never change the run outcome.
            pass

    def _notify(self, summary: RunSummary) -> None:
        """Fire completion notifications for the finished run (best-effort)."""
        if not self.config.notify_webhook and not self.config.notify_desktop:
            return
        notifications.notify_run_complete(
            summary,
            webhook_url=self.config.notify_webhook,
            desktop=self.config.notify_desktop,
            emit=lambda kind, **data: self._emit(kind, **data),
        )

    def _close_append_handles(self) -> None:
        for handle in self._append_handles.values():
            with contextlib.suppress(OSError):
                handle.close()
        self._append_handles.clear()

    def _write_summary(self, summary: RunSummary) -> None:
        """Persist the latest run summary so `owloop report` can read it."""
        summary_path = self.log_dir / "owloop_summary_latest.json"
        with summary_path.open("w", encoding="utf-8") as f:
            json.dump(summary.as_dict(), f, indent=2)
