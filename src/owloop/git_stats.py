"""Git history helpers for run summaries and reports."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CommitInfo:
    hash: str
    message: str
    author: str
    date: str
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0


def _run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def parse_git_stat(stat_output: str) -> tuple[int, int, int]:
    """Parse git show --stat summary line, e.g. '3 files changed, 12 insertions(+), 4 deletions(-)'."""
    files_changed = insertions = deletions = 0
    for line in stat_output.splitlines():
        if "files changed" in line or "file changed" in line:
            parts = line.split(",")
            for part in parts:
                part = part.strip()
                if "file" in part and "changed" in part:
                    files_changed = int(part.split()[0])
                elif "insertion" in part:
                    insertions = int(part.split()[0])
                elif "deletion" in part:
                    deletions = int(part.split()[0])
    return files_changed, insertions, deletions


def get_recent_commits(cwd: Path, iterations: int) -> list[CommitInfo]:
    """Return the last ``iterations`` commits on the current branch in ``cwd``."""
    if iterations <= 0:
        return []

    result = _run_git(cwd, "log", f"-{iterations}", "--format=%H|%an|%ad|%s", "--date=iso")
    if result.returncode != 0:
        return []

    commits: list[CommitInfo] = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("|", 3)
        if len(parts) != 4:
            continue
        commit_hash, author, date, message = parts
        stat = _run_git(cwd, "show", "--stat", "--format=", commit_hash)
        files_changed, insertions, deletions = parse_git_stat(stat.stdout)
        commits.append(
            CommitInfo(
                hash=commit_hash[:8],
                message=message,
                author=author,
                date=date,
                files_changed=files_changed,
                insertions=insertions,
                deletions=deletions,
            )
        )
    return commits


def total_diff_stats(commits: list[CommitInfo]) -> tuple[int, int, int]:
    """Sum files changed, insertions and deletions across ``commits``."""
    total_files = sum(c.files_changed for c in commits)
    total_ins = sum(c.insertions for c in commits)
    total_del = sum(c.deletions for c in commits)
    return total_files, total_ins, total_del
