"""Parallel workers over file-disjoint specs (Phase 4 of the #37 roadmap).

The community lesson for parallel Ralph-style loops is: invest in **file-disjoint
spec decomposition**, not lock coordination — schedule specs whose declared
``## Files`` scopes don't overlap so their worktrees can never conflict, then
merge the successful branches back with a plain ``git merge``. And never
parallelize before stall detection exists (Phase 1), because parallelism
multiplies the cost of missing progress.

Each worker runs one target spec in its own ``git worktree`` on its own branch:
implement → the *shared* deterministic gate (``verification.run_gate``) →
commit. The orchestrator then merges each passed branch into the base branch.
Because a batch is file-disjoint, those merges apply cleanly.

The gate is the same one the sequential engine uses, so the "harness verifies,
never the agent" invariant holds identically here.
"""

from __future__ import annotations

import shutil
import subprocess
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from owloop import notifications, spec_queue, verification
from owloop.adapters import AgentAdapter
from owloop.engine import RunSummary, StopReason, classify_terminal_state, spec_commit_subject
from owloop.paths import resolve_owloop_dir, resolve_specs_dir
from owloop.promise import parse_promise_signal

WORKER_PROMPT = """\
# Owloop — Parallel Build Worker

You are one of several workers running concurrently, each on a disjoint set of
files. Implement EXACTLY ONE spec and nothing else:

    {spec_name}

Read `AGENTS.md` / `CLAUDE.md` if present. Implement the spec completely and
run its `## Acceptance Criteria` commands yourself to check your work. Then
output `<promise>DONE</promise>`.

Stay strictly inside the files listed in that spec's `## Files` section — other
workers own the other files right now, and touching them will lose their work
at merge time. Do NOT work on any other spec.

The loop — not you — owns git and completion:
- Do NOT commit or push. The loop commits only after re-running the acceptance
  criteria itself and they pass.
- Do NOT add a `Status: COMPLETE` line, and do NOT edit the spec's
  `## Acceptance Criteria` / `## Verification` sections or
  `.owloop/backpressure.json`. Rewriting your own success conditions fails the
  iteration.

If you hit an external blocker, output `<promise>BLOCKED:reason</promise>`.
"""

EventCallback = Callable[[str, dict], None]
AdapterFactory = Callable[[], AgentAdapter]


@dataclass
class WorkerResult:
    spec_name: str
    passed: bool
    branch: str
    worktree: Path
    tampered: bool = False
    tokens_used: int = 0
    reason: str = ""


@dataclass
class ParallelConfig:
    project_dir: Path
    workers: int = 2
    max_rounds: int = 0  # 0 = until queue empty / stall
    max_consecutive_failed_rounds: int = 3
    notify_webhook: str | None = None
    notify_desktop: bool = False


class ParallelOrchestrator:
    """Run file-disjoint specs concurrently across per-worker git worktrees."""

    def __init__(
        self,
        config: ParallelConfig,
        adapter_factory: AdapterFactory,
        on_event: EventCallback | None = None,
    ) -> None:
        self.config = config
        self.adapter_factory = adapter_factory
        self.on_event = on_event or (lambda *_a: None)
        self.base_dir = config.project_dir
        self.session_id = uuid.uuid4().hex[:8]
        self.tokens_used = 0

    # ── git helpers ──

    def _git(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args],
            cwd=cwd or self.base_dir,
            capture_output=True,
            text=True,
        )

    def _is_git_repo(self) -> bool:
        return self._git("rev-parse", "--is-inside-work-tree").returncode == 0

    def _current_branch(self) -> str:
        return self._git("branch", "--show-current").stdout.strip() or "main"

    def _head(self) -> str:
        return str(self._git("rev-parse", "HEAD").stdout).strip()

    def _emit(self, kind: str, **data: object) -> None:
        self.on_event(kind, data)

    @property
    def specs_dir(self) -> Path:
        return resolve_specs_dir(self.base_dir)

    def preflight(self) -> list[str]:
        issues = self.adapter_factory().preflight()
        if not self._is_git_repo():
            issues.append("current directory is not a git repository")
        if not spec_queue.get_root_specs(self.specs_dir):
            issues.append("no .md files in specs/")
        return issues

    # ── worker ──

    def _run_worker(self, spec_name: str, base_head: str, index: int) -> WorkerResult:
        wt_base = self.base_dir.parent / f"{self.base_dir.name}-owloop-wt"
        wt_base.mkdir(parents=True, exist_ok=True)
        branch = f"owloop/{self.session_id}-w{index}"
        wt_path = wt_base / f"owloop-{self.session_id}-w{index}"

        created = self._git("worktree", "add", str(wt_path), "-b", branch, base_head)
        if created.returncode != 0:
            return WorkerResult(spec_name, False, branch, wt_path, reason="worktree_failed")

        # Materialize loop metadata (specs/backpressure) that may be untracked.
        source = resolve_owloop_dir(self.base_dir)
        if source.is_dir():
            shutil.copytree(source, wt_path / ".owloop", dirs_exist_ok=True)

        self._emit("worker_start", spec_name=spec_name, worker_id=index, branch=branch)

        wt_specs = resolve_specs_dir(wt_path)
        guard_before = verification.guarded_hash(wt_path, wt_specs, spec_name)

        adapter = self.adapter_factory()
        result = adapter.run(
            WORKER_PROMPT.format(spec_name=spec_name),
            cwd=wt_path,
            on_line=lambda line: self._emit("output_line", worker=index, line=line),
        )
        tokens = result.tokens_used
        parsed = parse_promise_signal(result.stdout)
        state = parsed[0] if parsed else ""

        if state != "DONE":
            self._emit("worker_no_done", spec_name=spec_name, worker_id=index)
            return WorkerResult(spec_name, False, branch, wt_path, tokens_used=tokens,
                                reason="no_done_signal")

        gate = verification.run_gate(wt_path, wt_specs, spec_name, guard_before)
        if gate.tampered:
            self._emit("spec_tampered", spec_name=spec_name, worker_id=index)
            return WorkerResult(spec_name, False, branch, wt_path, tampered=True,
                                tokens_used=tokens, reason="tampered")
        if not gate.passed:
            self._emit("verification_gate_failed", spec_name=spec_name, worker_id=index,
                       failed=gate.failed_count)
            return WorkerResult(spec_name, False, branch, wt_path, tokens_used=tokens,
                                reason="verification_failed")

        # Verified: mark complete + commit inside the worker's worktree.
        spec_queue.mark_spec_complete(wt_specs / spec_name)
        self._git("add", "-A", cwd=wt_path)
        # Unstage all owloop-internal metadata so it never enters project history.
        self._git("reset", "--quiet", "--", ".owloop/", cwd=wt_path)
        subject = spec_commit_subject(spec_name, wt_specs / spec_name)
        self._git("commit", "-m", subject, cwd=wt_path)
        self._emit("verification_gate_passed", spec_name=spec_name, worker_id=index,
                   passed=gate.passed_count)
        return WorkerResult(spec_name, True, branch, wt_path, tokens_used=tokens)

    def _cleanup_worker(self, result: WorkerResult, *, keep_branch: bool) -> None:
        self._git("worktree", "remove", "--force", str(result.worktree))
        if not keep_branch:
            self._git("branch", "-D", result.branch)

    # ── run ──

    def run(self) -> RunSummary:
        issues = self.preflight()
        if issues:
            self._emit("preflight_failed", issues=issues)
            return self._summary(StopReason.PREFLIGHT_FAILED, rounds=0, branch="", issues=issues)

        base_branch = self._current_branch()
        stopped_reason: StopReason = StopReason.SUCCESS
        rounds = 0
        consecutive_failed_rounds = 0

        self._emit("parallel_session_info", workers=self.config.workers,
                   branch=base_branch, session_id=self.session_id)

        while True:
            if self.config.max_rounds and rounds >= self.config.max_rounds:
                stopped_reason = StopReason.MAX_ITERATIONS
                break

            batch = spec_queue.get_parallel_batch(self.specs_dir, self.config.workers)
            if not batch:
                stopped_reason = StopReason.SUCCESS
                self._emit("all_specs_complete",
                           spec_count=spec_queue.count_root_specs(self.specs_dir))
                break

            rounds += 1
            base_head = self._head()
            names = [p.name for p in batch]
            self._emit("round_start", round=rounds, specs=names, size=len(names))

            results = self._run_batch(names, base_head)
            for r in results:
                self.tokens_used += r.tokens_used

            passed = [r for r in results if r.passed]
            self._merge_passed(passed, base_branch)
            for r in results:
                self._cleanup_worker(r, keep_branch=False)

            self._emit("round_end", round=rounds, passed=[r.spec_name for r in passed],
                       failed=[r.spec_name for r in results if not r.passed])

            if passed:
                consecutive_failed_rounds = 0
            else:
                consecutive_failed_rounds += 1
                if consecutive_failed_rounds >= self.config.max_consecutive_failed_rounds:
                    stopped_reason = StopReason.STALLED
                    self._emit("stalled", reason="no_progress_rounds",
                               rounds=consecutive_failed_rounds)
                    break

        summary = self._summary(stopped_reason, rounds=rounds, branch=base_branch)
        notifications.notify_run_complete(
            summary,
            webhook_url=self.config.notify_webhook,
            desktop=self.config.notify_desktop,
            emit=lambda kind, **data: self._emit(kind, **data),
        )
        return summary

    def _run_batch(self, names: list[str], base_head: str) -> list[WorkerResult]:
        if len(names) == 1:
            return [self._run_worker(names[0], base_head, 0)]
        with ThreadPoolExecutor(max_workers=len(names)) as pool:
            futures = [
                pool.submit(self._run_worker, name, base_head, i)
                for i, name in enumerate(names)
            ]
            return [f.result() for f in futures]

    def _merge_passed(self, passed: list[WorkerResult], base_branch: str) -> None:
        """Merge each verified worker branch into the base branch.

        The batch is file-disjoint, so these merges never conflict. Merges run
        sequentially in the base worktree in deterministic (spec-name) order.
        """
        for r in sorted(passed, key=lambda r: r.spec_name):
            merged = self._git("merge", "--no-ff", "-m",
                               f"owloop: merge {r.spec_name}", r.branch)
            if merged.returncode == 0:
                # The worker branch intentionally does not include .owloop/
                # metadata, so mark the spec complete in the base repo so the
                # queue sees progress and we don't loop forever.
                spec_queue.mark_spec_complete(self.specs_dir / r.spec_name)
                self._emit("worker_merged", spec_name=r.spec_name, branch=r.branch)
            else:
                # Should not happen for disjoint scopes; abort and surface it.
                self._git("merge", "--abort")
                self._emit("worker_merge_conflict", spec_name=r.spec_name, branch=r.branch)

    def _summary(
        self, stopped_reason: StopReason, *, rounds: int, branch: str,
        issues: list[str] | None = None,
    ) -> RunSummary:
        return RunSummary(
            iterations=rounds,
            branch=branch,
            cwd=self.base_dir,
            main_repo_dir=self.base_dir,
            stopped_reason=str(stopped_reason),
            terminal_state=classify_terminal_state(stopped_reason),
            issues=issues,
            tokens_used=self.tokens_used,
            session_id=self.session_id,
        )
