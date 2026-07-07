"""Session helpers for the owloop CLI."""

import json
import re
import subprocess
from pathlib import Path
from typing import Any

CHECKED_BOX_RE = re.compile(r"- \[[xX]\]")
# Mirrors the `**Status**: COMPLETE` convention spec_queue._COMPLETE_RE looks for,
# so `owloop status` classifies specs the same way the engine's queue does.
_STATUS_DONE_RE = re.compile(r"^(#{1,3} )?(\*\*)?status(\*\*)?:\s+complete", re.MULTILINE | re.IGNORECASE)
_STATUS_IN_PROGRESS_RE = re.compile(
    r"^(#{1,3} )?(\*\*)?status(\*\*)?:\s+in progress", re.MULTILINE | re.IGNORECASE
)


def classify_spec(content: str) -> str:
    if _STATUS_DONE_RE.search(content):
        return "done"
    if _STATUS_IN_PROGRESS_RE.search(content):
        return "in_progress"
    if CHECKED_BOX_RE.search(content):
        return "in_progress"
    return "pending"


def _read_latest_session(project_dir: Path) -> dict[str, Any] | None:
    """Load the latest session descriptor if it exists."""
    path = project_dir / ".owloop" / "logs" / "session_latest.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _find_worktree_path(project_dir: Path, session: dict[str, Any] | None = None) -> Path | None:
    """Return the worktree path from the session record or ``git worktree list``."""
    if session and session.get("path"):
        return Path(session["path"])
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            wt = Path(line.split(" ", 1)[1])
            if wt != project_dir and wt.name.startswith("owloop-"):
                return wt
    return None
