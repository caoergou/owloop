"""Operational learning tracker for cross-iteration memory.

When the agent discovers operational knowledge (e.g. "tests need a database",
"use poetry not pip") it is appended to `.owloop/learnings.md` so the next
iteration starts with that context instead of rediscovering it.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

LEARNINGS_FILE_NAME = "learnings.md"
LEARNING_RE = re.compile(r"<learning>(.*?)</learning>", re.DOTALL)


def learnings_path(project_dir: Path) -> Path:
    """Return the path to the operational learnings file."""
    return project_dir / ".owloop" / LEARNINGS_FILE_NAME


def load_learnings(project_dir: Path) -> str:
    """Return the current learnings markdown or an empty string."""
    path = learnings_path(project_dir)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def append_learning(project_dir: Path, text: str) -> Path:
    """Append a single learning entry to the learnings file."""
    path = learnings_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"## {timestamp}\n{text.strip()}\n\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(entry)
    return path


def extract_learnings(stdout: str) -> list[str]:
    """Extract `<learning>...</learning>` tags from agent output."""
    return [match.group(1).strip() for match in LEARNING_RE.finditer(stdout)]


def format_learnings_for_prompt(learnings: str) -> str:
    """Format learnings for injection into a build prompt."""
    if not learnings.strip():
        return ""
    return (
        "Operational learnings from previous iterations:\n\n"
        f"{learnings.strip()}\n\n"
        "Apply these learnings to avoid repeating discovered blockers. "
        "If you discover a new operational fact, wrap it in `<learning>...</learning>` "
        "so it is recorded for future iterations."
    )
