"""The deterministic verification gate — the single place work is graded.

owloop's central invariant (#32): completion is decided by the *harness* running
the spec's acceptance criteria + the project's backpressure commands via
``subprocess``, outside the agent's control, never by the agent's own say-so. A
snapshot hash of the sections the agent must not touch (acceptance criteria,
verification, ``backpressure.json``) catches an agent that rewrites its own
success conditions.

Both the sequential engine and the parallel orchestrator call these functions,
so the gate is shared, not duplicated — there is exactly one definition of
"verified".
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from owloop import spec_queue
from owloop.backpressure import load_backpressure
from owloop.paths import resolve_owloop_dir


@dataclass
class GateResult:
    passed: bool
    tampered: bool
    passed_count: int
    failed_count: int
    failures: list[dict[str, Any]] = field(default_factory=list)
    # True when functional checks pass but a structural/meta check (e.g. grep)
    # failed. The engine should surface the diff for human review rather than
    # blindly rolling back work that may be correct.
    soft_failure: bool = False


def run_commands(
    cwd: Path, commands: list[str]
) -> tuple[int, int, list[dict[str, Any]]]:
    """Run shell commands from the harness (not the agent).

    Returns ``(passed, failed, failures)`` where each failure records the
    command, its exit code, and an output tail for failure feedback.
    """
    passed = failed = 0
    failures: list[dict[str, Any]] = []
    for command in commands:
        result = subprocess.run(  # noqa: S602 - spec-authored commands, same trust model as the agent's own execution
            command, shell=True, cwd=cwd, capture_output=True, text=True,
        )
        if result.returncode == 0:
            passed += 1
        else:
            failed += 1
            output = f"{result.stdout or ''}\n{result.stderr or ''}".strip()
            tail = "\n".join(output.splitlines()[-30:])[-2000:]
            failures.append(
                {"command": command, "returncode": result.returncode, "output": tail}
            )
    return passed, failed, failures


def _tail_output(result: subprocess.CompletedProcess[str]) -> str:
    output = f"{result.stdout or ''}\n{result.stderr or ''}".strip()
    return "\n".join(output.splitlines()[-30:])[-2000:]


def run_acceptance_criteria(
    cwd: Path, specs_dir: Path, spec_name: str | None
) -> tuple[int, int, list[dict[str, Any]], int, int]:
    """Run a spec's Acceptance Criteria shell commands; count passes vs failures.

    Returns ``(passed, failed, failures, code_failed, meta_failed)`` where
    ``code_failed`` counts functional checks (tests, lints) and ``meta_failed``
    counts structural checks such as ``grep ... → no output``.
    """
    if not spec_name:
        return 0, 0, [], 0, 0

    criteria = spec_queue.get_acceptance_criteria_commands(specs_dir / spec_name)
    passed = failed = code_failed = meta_failed = 0
    failures: list[dict[str, Any]] = []
    for criterion in criteria:
        result = subprocess.run(  # noqa: S602
            criterion.command, shell=True, cwd=cwd, capture_output=True, text=True,
        )
        if criterion.expect_no_output:
            # grep-style tools exit 1 when they find no matches; the expectation
            # is about empty stdout, not the exit code.
            ok = result.stdout.strip() == "" and result.returncode in (0, 1)
            is_meta = True
        else:
            ok = result.returncode == 0
            is_meta = False

        if ok:
            passed += 1
        else:
            failed += 1
            if is_meta:
                meta_failed += 1
            else:
                code_failed += 1
            failures.append(
                {
                    "command": criterion.command,
                    "returncode": result.returncode,
                    "output": _tail_output(result),
                }
            )
    return passed, failed, failures, code_failed, meta_failed


def _restore_exclusions(cwd: Path, specs_dir: Path, spec_name: str | None) -> None:
    """Revert any tracked files listed in the spec's Exclusions section.

    Acceptance-criteria commands (e.g. ``uv run --with pytest``) can mutate
    files the spec promised not to touch, such as ``uv.lock``. This best-effort
    cleanup restores those tracked files to HEAD so they never leak into the
    iteration's commit.
    """
    if not spec_name:
        return
    exclusions = spec_queue.get_spec_exclusions(specs_dir / spec_name)
    if not exclusions:
        return
    for pattern in exclusions:
        result = subprocess.run(
            ["git", "ls-files", "--", pattern],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
        if files:
            subprocess.run(
                ["git", "checkout", "--", *files],
                cwd=cwd,
                capture_output=True,
            )


def guarded_hash(cwd: Path, specs_dir: Path, spec_name: str | None) -> str:
    """Hash the spec sections + backpressure file the agent must not edit."""
    h = hashlib.sha256()
    if spec_name:
        section = spec_queue.get_acceptance_criteria_section(specs_dir / spec_name)
        h.update(section.encode("utf-8"))
    backpressure = resolve_owloop_dir(cwd) / "backpressure.json"
    if backpressure.is_file():
        h.update(backpressure.read_bytes())
    return h.hexdigest()


def run_gate(
    cwd: Path, specs_dir: Path, spec_name: str | None, guard_before: str
) -> GateResult:
    """Deterministically verify one iteration's work outside the agent's control.

    A guard region that changed since ``guard_before`` fails immediately as
    ``tampered``; otherwise the acceptance-criteria and backpressure commands
    decide pass/fail by exit code.
    """
    if guarded_hash(cwd, specs_dir, spec_name) != guard_before:
        return GateResult(passed=False, tampered=True, passed_count=0, failed_count=0)

    acc_passed, acc_failed, acc_failures, acc_code_failed, acc_meta_failed = run_acceptance_criteria(
        cwd, specs_dir, spec_name
    )
    _restore_exclusions(cwd, specs_dir, spec_name)

    bp_commands = [cmd.command for cmd in load_backpressure(cwd)]
    bp_passed, bp_failed, bp_failures = run_commands(cwd, bp_commands)
    _restore_exclusions(cwd, specs_dir, spec_name)

    passed_count = acc_passed + bp_passed
    failed_count = acc_failed + bp_failed
    # Soft failure: functional checks (code + backpressure) pass, but a
    # structural/meta check failed. Surface for human review instead of rolling
    # back potentially-correct work.
    soft_failure = failed_count > 0 and acc_code_failed == 0 and bp_failed == 0
    return GateResult(
        passed=failed_count == 0,
        tampered=False,
        passed_count=passed_count,
        failed_count=failed_count,
        failures=acc_failures + bp_failures,
        soft_failure=soft_failure,
    )
