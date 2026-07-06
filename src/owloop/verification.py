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
from dataclasses import dataclass
from pathlib import Path

from owloop import spec_queue
from owloop.backpressure import load_backpressure
from owloop.paths import resolve_owloop_dir


@dataclass
class GateResult:
    passed: bool
    tampered: bool
    passed_count: int
    failed_count: int


def run_commands(cwd: Path, commands: list[str]) -> tuple[int, int]:
    """Run shell commands from the harness (not the agent); count pass/fail."""
    passed = failed = 0
    for command in commands:
        result = subprocess.run(  # noqa: S602 - spec-authored commands, same trust model as the agent's own execution
            command, shell=True, cwd=cwd, capture_output=True, text=True,
        )
        if result.returncode == 0:
            passed += 1
        else:
            failed += 1
    return passed, failed


def run_acceptance_criteria(cwd: Path, specs_dir: Path, spec_name: str | None) -> tuple[int, int]:
    """Run a spec's Acceptance Criteria shell commands; count passes vs failures."""
    if not spec_name:
        return 0, 0
    commands = spec_queue.get_acceptance_criteria_commands(specs_dir / spec_name)
    return run_commands(cwd, commands)


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

    acc_passed, acc_failed = run_acceptance_criteria(cwd, specs_dir, spec_name)
    bp_commands = [cmd.command for cmd in load_backpressure(cwd)]
    bp_passed, bp_failed = run_commands(cwd, bp_commands)

    passed_count = acc_passed + bp_passed
    failed_count = acc_failed + bp_failed
    return GateResult(
        passed=failed_count == 0,
        tampered=False,
        passed_count=passed_count,
        failed_count=failed_count,
    )
