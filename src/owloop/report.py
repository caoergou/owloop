"""Generate an HTML summary report for the latest owloop run."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from owloop._brand import AMBER, DIM_BLUE, MOON_WHITE, NIGHT, OWL_MEDIUM


@dataclass
class CommitInfo:
    hash: str
    message: str
    author: str
    date: str
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0


class ReportGenerator:
    """Build a branded HTML report from the latest run summary and git history."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir
        self.summary_path = project_dir / "logs" / "owloop_summary_latest.json"

    def _run_git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args],
            cwd=self.project_dir,
            capture_output=True,
            text=True,
        )

    def _load_summary(self) -> dict[str, Any]:
        if self.summary_path.exists():
            with self.summary_path.open() as f:
                return json.load(f)  # type: ignore[no-any-return]
        return {}

    def _commits_since(self, branch: str, iterations: int) -> list[CommitInfo]:
        """Return the last N commits on the current branch."""
        result = self._run_git("log", f"-{iterations}", "--format=%H|%an|%ad|%s", "--date=iso")
        if result.returncode != 0:
            return []

        commits = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("|", 3)
            if len(parts) != 4:
                continue
            commit_hash, author, date, message = parts
            stat = self._run_git("show", "--stat", "--format=", commit_hash)
            files_changed, insertions, deletions = self._parse_stat(stat.stdout)
            commits.append(CommitInfo(
                hash=commit_hash[:8],
                message=message,
                author=author,
                date=date,
                files_changed=files_changed,
                insertions=insertions,
                deletions=deletions,
            ))
        return commits

    @staticmethod
    def _parse_stat(stat_output: str) -> tuple[int, int, int]:
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

    def _total_diff_stats(self, commits: list[CommitInfo]) -> tuple[int, int, int]:
        total_files = sum(c.files_changed for c in commits)
        total_ins = sum(c.insertions for c in commits)
        total_del = sum(c.deletions for c in commits)
        return total_files, total_ins, total_del

    def generate(self, output_path: Path | None = None) -> Path:
        summary = self._load_summary()
        branch = summary.get("branch", "unknown")
        iterations = summary.get("iterations", 0)
        tokens_used = summary.get("tokens_used", 0)
        stopped_reason = summary.get("stopped_reason", "unknown")
        commits = self._commits_since(branch, iterations)
        total_files, total_ins, total_del = self._total_diff_stats(commits)

        report_file = output_path or (self.project_dir / "logs" / "owloop_report.html")
        report_file.parent.mkdir(parents=True, exist_ok=True)

        html = self._render_html(
            branch=branch,
            iterations=iterations,
            tokens_used=tokens_used,
            stopped_reason=stopped_reason,
            commits=commits,
            total_files=total_files,
            total_ins=total_ins,
            total_del=total_del,
        )
        report_file.write_text(html)
        return report_file

    def _render_html(
        self,
        branch: str,
        iterations: int,
        tokens_used: int,
        stopped_reason: str,
        commits: list[CommitInfo],
        total_files: int,
        total_ins: int,
        total_del: int,
    ) -> str:
        owl = "<br>".join(OWL_MEDIUM).replace(" ", "&nbsp;")
        rows = "\n".join(self._commit_row(c) for c in commits)
        token_line = f"<p><strong>Tokens used:</strong> {tokens_used:,}</p>" if tokens_used else ""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>owloop report — {branch}</title>
<style>
  :root {{ --night: {NIGHT}; --amber: {AMBER}; --moon: {MOON_WHITE}; --dim: {DIM_BLUE}; }}
  body {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
         background: var(--night); color: var(--moon); margin: 0; padding: 2rem; }}
  .container {{ max-width: 900px; margin: 0 auto; }}
  header {{ text-align: center; border-bottom: 2px solid var(--amber); padding-bottom: 1rem; margin-bottom: 2rem; }}
  .owl {{ color: var(--amber); font-size: 0.9rem; line-height: 1.1; white-space: pre; }}
  h1 {{ color: var(--amber); margin: 0.5rem 0; }}
  .meta {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin: 2rem 0; }}
  .card {{ background: rgba(255,255,255,0.03); border: 1px solid var(--dim); border-radius: 8px; padding: 1rem; }}
  .card h3 {{ color: var(--amber); margin-top: 0; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
  th, td {{ text-align: left; padding: 0.6rem; border-bottom: 1px solid var(--dim); }}
  th {{ color: var(--amber); }}
  .stats {{ color: #8fd19e; }}
  .del {{ color: #e0777d; }}
  footer {{ margin-top: 3rem; text-align: center; color: var(--dim); font-size: 0.85rem; }}
  code {{ background: rgba(255,255,255,0.08); padding: 0.2rem 0.4rem; border-radius: 4px; }}
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="owl">{owl}</div>
    <h1>owloop report</h1>
    <p>Your code evolves while you sleep.</p>
  </header>

  <section class="meta">
    <div class="card"><h3>Branch</h3><p><code>{branch}</code></p></div>
    <div class="card"><h3>Iterations</h3><p>{iterations}</p></div>
    <div class="card"><h3>Status</h3><p>{stopped_reason}</p></div>
    <div class="card"><h3>Total diff</h3><p>{total_files} files · <span class="stats">+{total_ins}</span> · <span class="del">-{total_del}</span></p></div>
  </section>
  {token_line}

  <h2>Commits</h2>
  <table>
    <thead>
      <tr><th>Commit</th><th>Message</th><th>Author</th><th>Date</th><th>Changes</th></tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>

  <footer>
    <p>Generated by owloop on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
    <p>Review: <code>git log --oneline HEAD~{iterations}..HEAD</code></p>
  </footer>
</div>
</body>
</html>"""

    def _commit_row(self, commit: CommitInfo) -> str:
        return (
            f"<tr>"
            f"<td><code>{commit.hash}</code></td>"
            f"<td>{commit.message}</td>"
            f"<td>{commit.author}</td>"
            f"<td>{commit.date}</td>"
            f"<td>{commit.files_changed} files · "
            f"<span class=\"stats\">+{commit.insertions}</span> · "
            f"<span class=\"del\">-{commit.deletions}</span></td>"
            f"</tr>"
        )
