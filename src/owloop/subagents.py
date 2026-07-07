"""Subagent orchestration for large specs.

When enabled, a large iteration is split into focused phases so each subagent
gets a smaller context window and a single responsibility.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from owloop.adapters import AgentAdapter, AgentResult

OnLine = Callable[[str], None]


ORIENT_PROMPT = """\
# Owloop — Orient Phase

You are the orient subagent. Read the highest-priority incomplete spec in
specs/ and the relevant source files. Do NOT write code.

Produce a focused implementation plan with:
1. The exact files to modify (1-5 files).
2. A step-by-step plan for each file.
3. The verification commands to run after implementation.

Output only the plan, then `<promise>DONE</promise>`.
"""

IMPLEMENT_PROMPT = """\
# Owloop — Implement Phase

You are the implement subagent. You receive a plan from the orient phase.

{plan}

Implement the changes described in the plan. Stay within the listed files.
Run the verification commands. When complete, output `<promise>DONE</promise>`.
"""


@dataclass
class SubagentPlan:
    """Output of the orient subagent."""

    text: str
    files: list[str]


class SubagentOrchestrator:
    """Run a single large iteration as orient → implement → verify phases."""

    def __init__(
        self,
        adapter: AgentAdapter,
        verifier_adapter: AgentAdapter | None,
        cwd: Path,
        on_line: OnLine | None = None,
    ) -> None:
        self.adapter = adapter
        self.verifier_adapter = verifier_adapter
        self.cwd = cwd
        self.on_line = on_line

    def run(self) -> AgentResult:
        """Execute the phased workflow and return a single combined result."""
        orient_result = self._run_orient()
        if orient_result.promise_state != "DONE":
            return orient_result

        plan = orient_result.stdout
        implement_result = self._run_implement(plan)
        if implement_result.promise_state != "DONE":
            return implement_result

        if self.verifier_adapter is not None:
            verify_result = self._run_verify()
            return self._merge_results(orient_result, implement_result, verify_result)

        return self._merge_results(orient_result, implement_result)

    def _run_orient(self) -> AgentResult:
        return self.adapter.run(ORIENT_PROMPT, cwd=self.cwd, on_line=self.on_line)

    def _run_implement(self, plan: str) -> AgentResult:
        prompt = IMPLEMENT_PROMPT.format(plan=plan)
        return self.adapter.run(prompt, cwd=self.cwd, on_line=self.on_line)

    def _run_verify(self) -> AgentResult:
        from owloop.engine import VERIFIER_PROMPT

        return self.verifier_adapter.run(  # type: ignore[union-attr]
            VERIFIER_PROMPT, cwd=self.cwd, on_line=self.on_line
        )

    @staticmethod
    def _merge_results(
        orient: AgentResult, implement: AgentResult, verify: AgentResult | None = None
    ) -> AgentResult:
        stdout_parts = ["## Orient\n", orient.stdout, "\n## Implement\n", implement.stdout]
        tokens_used = orient.tokens_used + implement.tokens_used
        cost_usd = orient.cost_usd + implement.cost_usd
        if verify is not None:
            stdout_parts.extend(["\n## Verify\n", verify.stdout])
            tokens_used += verify.tokens_used
            cost_usd += verify.cost_usd

        combined = "".join(stdout_parts)
        success = implement.success and implement.promise_state == "DONE"
        promise_state = implement.promise_state
        if verify is not None and verify.promise_state != "PASS":
            success = False
            promise_state = "VERIFY_FAIL"

        return AgentResult(
            stdout=combined,
            returncode=implement.returncode,
            success=success,
            has_completion_signal=implement.has_completion_signal,
            done_signal=implement.done_signal,
            timed_out=implement.timed_out,
            tokens_used=tokens_used,
            cost_usd=cost_usd,
            promise_state=promise_state,
            promise_payload=verify.promise_payload if verify else implement.promise_payload,
        )
