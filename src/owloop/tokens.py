"""Token usage tracking for agent iterations.

Claude Code CLI does not emit a stable, documented token-usage line today.
Instead of hard-coding one format, owloop scans agent output with a set of
common regex patterns and sums the largest number found per iteration. Users
who need exact accounting can pipe output through a wrapper that prints a
recognisable token line.
"""

from __future__ import annotations

import re

# Patterns ordered from most to least specific. Each regex should contain at
# least one capturing group that is the token count. When multiple groups are
# present (input + output) they are summed.
DEFAULT_PATTERNS = [
    # Claude API-style JSON usage block
    re.compile(r'"input_tokens"\s*:\s*(\d+).*?"output_tokens"\s*:\s*(\d+)', re.IGNORECASE),
    re.compile(r'"prompt_tokens"\s*:\s*(\d+).*?"completion_tokens"\s*:\s*(\d+)', re.IGNORECASE),
    # Explicit total lines
    re.compile(r'total tokens\s*[:=]\s*(\d+)', re.IGNORECASE),
    re.compile(r'(?:used|consumed)\s+(\d+)\s+tokens', re.IGNORECASE),
    # Input / output split lines
    re.compile(r'input tokens\s*[:=]\s*(\d+)', re.IGNORECASE),
    re.compile(r'output tokens\s*[:=]\s*(\d+)', re.IGNORECASE),
    # Generic "Tokens: 1234" fallback
    re.compile(r'tokens\s*[:=]\s*(\d+)', re.IGNORECASE),
]


class IterationTokenLimitExceededError(Exception):
    """Raised from an ``on_line`` callback to signal a per-iteration token cap breach.

    Adapters that stream output (see ``StreamingAgentAdapter.run()``) let this
    propagate out of their read loop, killing the underlying process, so the
    caller (``OwloopEngine.run_iteration()``) can turn it into a failed
    iteration instead of letting a runaway agent keep burning tokens.
    """

    def __init__(self, tokens_used: int) -> None:
        super().__init__(f"iteration token limit exceeded: {tokens_used} tokens")
        self.tokens_used = tokens_used


class TokenTracker:
    """Extract token counts from agent output lines.

    The tracker is intentionally permissive: if an iteration prints token
    usage in any recognised shape, it is captured. If nothing matches, the
    iteration reports zero tokens rather than failing the run.

    Adapters that know their exact usage (e.g. from a structured `result`
    stream event) can call ``record_usage`` as soon as it arrives instead of
    waiting for the regex fallback to scan the final output. Once explicit
    usage has been recorded, ``resolve()`` prefers it over the heuristic.
    """

    def __init__(self, patterns: list[re.Pattern] | None = None) -> None:
        self.patterns = patterns or list(DEFAULT_PATTERNS)
        self._explicit_tokens = 0
        self._explicit_cost_usd = 0.0
        self._has_explicit_usage = False

    def record_usage(self, *, input_tokens: int = 0, output_tokens: int = 0, cost_usd: float = 0.0) -> int:
        """Record explicit usage reported by the agent stream.

        Returns the running explicit token total so callers can check it
        against a cap without a separate accessor.
        """
        self._explicit_tokens += input_tokens + output_tokens
        self._explicit_cost_usd += cost_usd
        self._has_explicit_usage = True
        return self._explicit_tokens

    @property
    def has_explicit_usage(self) -> bool:
        return self._has_explicit_usage

    @property
    def cost_usd(self) -> float:
        return self._explicit_cost_usd

    def reset(self) -> None:
        """Clear recorded explicit usage, e.g. between iterations sharing one tracker."""
        self._explicit_tokens = 0
        self._explicit_cost_usd = 0.0
        self._has_explicit_usage = False

    def resolve(self, text: str) -> int:
        """Return the token count for a finished iteration.

        Prefers explicit usage recorded via ``record_usage``; falls back to
        the regex/heuristic scan of ``text`` when no explicit usage arrived.
        """
        if self._has_explicit_usage:
            return self._explicit_tokens
        return self.count_from_text(text)

    def count_from_line(self, line: str) -> int:
        """Return the token count found in a single output line, or 0."""
        total = 0
        matched = False
        for pattern in self.patterns:
            match = pattern.search(line)
            if match:
                matched = True
                for group in match.groups():
                    if group is not None:
                        total += int(group)
                # Stop after the first pattern that matches this line to avoid
                # double-counting from overlapping generic patterns.
                break
        return total if matched else 0

    def count_from_text(self, text: str) -> int:
        """Return the total token count found across all lines of output."""
        return sum(self.count_from_line(line) for line in text.splitlines())
