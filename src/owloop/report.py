"""Generate a branded HTML summary report for the latest owloop run."""

from __future__ import annotations

import html
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from owloop._brand import OWL_MEDIUM
from owloop.report_design_system import base_styles, tailwind_cdn


@dataclass
class CommitInfo:
    hash: str
    message: str
    author: str
    date: str
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0


@dataclass
class ReportInsights:
    """Optional AI-generated content slots.

    These are intentionally separate from the raw data so that:
    - The report generator can render without any LLM call (fast, free, offline).
    - An external caller (e.g. the engine or a future `--report-ai` flag) can
      fill the slots with natural-language analysis when desired.
    """

    summary: str = ""
    risks: list[str] | None = None
    review_focus: list[str] | None = None

    def has_content(self) -> bool:
        return bool(self.summary or self.risks or self.review_focus)


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
            with self.summary_path.open(encoding="utf-8") as f:
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

    def generate(
        self,
        output_path: Path | None = None,
        insights: ReportInsights | None = None,
        use_tailwind: bool = False,
    ) -> Path:
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
            insights=insights or ReportInsights(),
            use_tailwind=use_tailwind,
        )
        report_file.write_text(html, encoding="utf-8")
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
        insights: ReportInsights,
        use_tailwind: bool,
    ) -> str:
        owl = "<br>".join(OWL_MEDIUM).replace(" ", "&nbsp;")
        rows = "\n".join(self._commit_row(c) for c in commits)
        status_badge = self._status_badge(stopped_reason)
        token_card = self._token_card(tokens_used)
        insights_section = self._insights_section(insights)
        tailwind = tailwind_cdn() if use_tailwind else ""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>owloop report — {html.escape(branch)}</title>
{tailwind}
<style>
{base_styles()}
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
    <div class="card"><h3>Branch</h3><p><code>{html.escape(branch)}</code></p></div>
    <div class="card"><h3>Iterations</h3><p>{iterations}</p></div>
    <div class="card"><h3>Status</h3><p>{status_badge}</p></div>
    <div class="card"><h3>Total diff</h3><p>{total_files} files · <span class="stats">+{total_ins}</span> · <span class="del">-{total_del}</span></p></div>
    {token_card}
  </section>

  {insights_section}

  <h2>Commits</h2>
  <table>
    <thead>
      <tr><th>Commit</th><th>Message</th><th>Author</th><th>Date</th><th>Changes</th></tr>
    </thead>
    <tbody>
      {rows if rows else '<tr><td colspan="5" class="empty">No commits recorded for this run.</td></tr>'}
    </tbody>
  </table>

  <footer>
    <p>Generated by owloop on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
    <p>Review: <code>git log --oneline HEAD~{iterations}..HEAD</code></p>
  </footer>
</div>
</body>
</html>"""

    @staticmethod
    def _status_badge(stopped_reason: str) -> str:
        reason = stopped_reason.lower()
        if reason in {"completed", "done", "success"}:
            css = "badge badge-success"
            label = "Completed"
        elif reason in {"blocked", "failure", "error"}:
            css = "badge badge-danger"
            label = "Blocked"
        else:
            css = "badge badge-info"
            label = stopped_reason
        return f'<span class="{css}">{html.escape(label)}</span>'

    @staticmethod
    def _token_card(tokens_used: int) -> str:
        if not tokens_used:
            return ""
        return f'<div class="card"><h3>Tokens used</h3><p>{tokens_used:,}</p></div>'

    def _insights_section(self, insights: ReportInsights) -> str:
        if not insights.has_content():
            return ""

        parts = ['<section class="insights"><h2>Insights</h2>']
        if insights.summary:
            parts.append(
                f'<div class="insight"><h4>Summary</h4><p>{html.escape(insights.summary)}</p></div>'
            )
        if insights.risks:
            parts.append(self._insight_list("Risks to review", insights.risks, "del"))
        if insights.review_focus:
            parts.append(self._insight_list("Review focus", insights.review_focus, "stats"))
        parts.append("</section>")
        return "\n".join(parts)

    @staticmethod
    def _insight_list(title: str, items: list[str], marker_class: str) -> str:
        lines = [f'<div class="insight"><h4>{html.escape(title)}</h4><ul>']
        for item in items:
            lines.append(f'<li><span class="{marker_class}">•</span> {html.escape(item)}</li>')
        lines.append("</ul></div>")
        return "\n".join(lines)

    def _commit_row(self, commit: CommitInfo) -> str:
        return (
            f"<tr>"
            f"<td><code>{html.escape(commit.hash)}</code></td>"
            f"<td>{html.escape(commit.message)}</td>"
            f"<td>{html.escape(commit.author)}</td>"
            f"<td>{html.escape(commit.date)}</td>"
            f"<td>{commit.files_changed} files · "
            f'<span class="stats">+{commit.insertions}</span> · '
            f'<span class="del">-{commit.deletions}</span></td>'
            f"</tr>"
        )
