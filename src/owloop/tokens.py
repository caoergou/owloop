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


class TokenTracker:
    """Extract token counts from agent output lines.

    The tracker is intentionally permissive: if an iteration prints token
    usage in any recognised shape, it is captured. If nothing matches, the
    iteration reports zero tokens rather than failing the run.
    """

    def __init__(self, patterns: list[re.Pattern] | None = None) -> None:
        self.patterns = patterns or list(DEFAULT_PATTERNS)

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
