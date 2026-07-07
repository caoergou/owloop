"""Generate a branded HTML summary report for the latest owloop run."""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from owloop._brand import OWL_MEDIUM
from owloop.git_stats import CommitInfo, get_recent_commits, total_diff_stats
from owloop.paths import resolve_logs_dir, resolve_specs_dir
from owloop.report_ai import (
    KeyChange,
    NextAction,
    ReportInsights,
    ReviewFocus,
    Risk,
)
from owloop.report_design_system import base_styles, google_fonts_link, tailwind_cdn
from owloop.spec_queue import get_root_specs, is_root_spec_complete


class ReportGenerator:
    """Build a branded HTML report from the latest run summary and git history."""

    FAILURE_EVENT_KINDS = {
        "agent_failed",
        "agent_timeout",
        "verification_failed",
        "verification_gate_failed",
        "spec_tampered",
        "stalled",
        "iteration_exhausted",
        "blocked",
        "decide",
        "max_tokens_reached",
        "max_duration_reached",
        "fix_loop_blocked",
        "interrupted",
        "preflight_failed",
    }

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir
        logs_dir = resolve_logs_dir(project_dir)
        self.summary_path = logs_dir / "owloop_summary_latest.json"
        self.events_path = logs_dir / "events.jsonl"

    def _load_summary(self) -> dict[str, Any]:
        if self.summary_path.exists():
            with self.summary_path.open(encoding="utf-8") as f:
                return json.load(f)  # type: ignore[no-any-return]
        # The engine writes the detailed summary inside the worktree; the main
        # repo only gets a lightweight session file. Fall back to it so reports
        # generated from the main repo still show branch/iterations/status.
        session_path = self.summary_path.with_name("session_latest.json")
        if session_path.exists():
            with session_path.open(encoding="utf-8") as f:
                session = json.load(f)  # type: ignore[no-any-return]
            status = session.get("status", "unknown")
            # The session file uses "completed" as a generic completion flag;
            # the classifier expects the granular stopped_reason "success".
            stopped_reason = "success" if status == "completed" else status
            return {
                "iterations": session.get("iterations", 0),
                "branch": session.get("branch", "unknown"),
                "tokens_used": session.get("tokens_used", 0),
                "estimated_cost_usd": 0,
                "stopped_reason": stopped_reason,
            }
        return {}

    def _load_events(self) -> list[dict[str, Any]]:
        if not self.events_path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in self.events_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events

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
        estimated_cost_usd = summary.get("estimated_cost_usd", 0)
        stopped_reason = summary.get("stopped_reason", "unknown")
        commits = get_recent_commits(self.project_dir, iterations)
        total_files, total_ins, total_del = total_diff_stats(commits)

        report_file = output_path or (resolve_logs_dir(self.project_dir) / "owloop_report.html")
        report_file.parent.mkdir(parents=True, exist_ok=True)

        html = self._render_html(
            branch=branch,
            iterations=iterations,
            tokens_used=tokens_used,
            estimated_cost_usd=estimated_cost_usd,
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
        estimated_cost_usd: float,
        stopped_reason: str,
        commits: list[CommitInfo],
        total_files: int,
        total_ins: int,
        total_del: int,
        insights: ReportInsights,
        use_tailwind: bool,
    ) -> str:
        owl = "<br>".join(OWL_MEDIUM).replace(" ", "&nbsp;")
        commit_rows = "\n".join(self._commit_row(c) for c in commits)
        spec_rows = self._spec_status_rows()
        diff_summary = self._diff_summary(iterations)
        status_badge = self._status_badge(stopped_reason)
        token_card = self._token_card(tokens_used)
        cost_card = self._cost_card(estimated_cost_usd)
        insights_section = self._insights_section(insights)
        events_section = self._events_section(stopped_reason)
        tailwind = tailwind_cdn() if use_tailwind else ""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>owloop report — {html.escape(branch)}</title>
{google_fonts_link()}
{tailwind}
<style>
{base_styles()}
.section {{ margin-top: 2.5rem; }}
.section-title {{
  font-family: var(--owl-font-sans);
  color: var(--owl-amber);
  font-size: 1.4rem;
  border-bottom: 1px solid var(--owl-dim-blue);
  padding-bottom: 0.4rem;
  margin-bottom: 1rem;
}}
.grid-2 {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 1rem;
}}
.diff-stat {{
  background: var(--owl-night-card);
  border: 1px solid var(--owl-dim-blue);
  border-radius: 8px;
  padding: 1rem;
  overflow-x: auto;
  font-size: 0.85rem;
  line-height: 1.5;
}}
.insight-summary {{
  background: var(--owl-night-card);
  border-left: 4px solid var(--owl-amber);
  padding: 1rem 1.25rem;
  border-radius: 0 8px 8px 0;
  margin: 1rem 0;
}}
.insight-summary h4 {{
  color: var(--owl-amber-bright);
  margin: 0 0 0.5rem 0;
  font-family: var(--owl-font-sans);
}}
.action-list {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 1rem;
  margin-top: 1rem;
}}
.action-card {{
  background: var(--owl-night-card);
  border: 1px solid var(--owl-dim-blue);
  border-radius: 8px;
  padding: 1rem;
}}
.action-card p {{ margin: 0.5rem 0 0 0; }}
h3 {{
  color: var(--owl-amber-bright);
  font-family: var(--owl-font-sans);
  font-size: 1.1rem;
  margin-top: 1.5rem;
  margin-bottom: 0.5rem;
}}
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="owl">{owl}</div>
    <h1 style="font-family: var(--owl-font-display);">owloop report</h1>
    <p style="font-family: var(--owl-font-tagline); font-size: 1.3rem;">Your code evolves while you sleep.</p>
  </header>

  <section class="meta">
    <div class="card"><h3>Branch</h3><p><code>{html.escape(branch)}</code></p></div>
    <div class="card"><h3>Iterations</h3><p>{iterations}</p></div>
    <div class="card"><h3>Status</h3><p>{status_badge}</p></div>
    <div class="card"><h3>Total diff</h3><p>{total_files} files · <span class="stats">+{total_ins}</span> · <span class="del">-{total_del}</span></p></div>
    {token_card}
    {cost_card}
  </section>

  {insights_section}

  <section class="section">
    <h2 class="section-title">Spec Status</h2>
    <table>
      <thead>
        <tr><th>Spec</th><th>Priority</th><th>Status</th></tr>
      </thead>
      <tbody>
        {spec_rows}
      </tbody>
    </table>
  </section>

  <section class="section">
    <h2 class="section-title">Diff Summary</h2>
    {diff_summary}
  </section>

  {events_section}

  <section class="section">
    <h2 class="section-title">Commits</h2>
    <table>
      <thead>
        <tr><th>Commit</th><th>Message</th><th>Author</th><th>Date</th><th>Changes</th></tr>
      </thead>
      <tbody>
        {commit_rows if commit_rows else '<tr><td colspan="5" class="empty">No commits recorded for this run.</td></tr>'}
      </tbody>
    </table>
  </section>

  <footer>
    <p>Generated by owloop on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
    <p>Branch diff: <code>{total_files} files · +{total_ins} · -{total_del}</code></p>
    <p>Review:</p>
    <ul>
      <li><code>git log --oneline HEAD~{iterations}..HEAD</code></li>
      <li><code>git diff --stat HEAD~{iterations}..HEAD</code></li>
    </ul>
  </footer>
</div>
</body>
</html>"""

    @staticmethod
    def _status_badge(stopped_reason: str) -> str:
        from owloop.engine import TerminalState, classify_terminal_state

        state = classify_terminal_state(stopped_reason)
        # `exhausted` and `stalled` are outcomes, not successes — badge them as
        # danger so a budget-exhausted run never reads as "Completed".
        if state == TerminalState.SUCCESS:
            css, label = "badge badge-success", "Completed"
        elif state == TerminalState.EXHAUSTED:
            css, label = "badge badge-danger", f"Exhausted ({stopped_reason})"
        elif state in {TerminalState.STALLED, TerminalState.BLOCKED, TerminalState.TAMPERED, TerminalState.FAILED}:
            css, label = "badge badge-danger", stopped_reason
        else:
            css, label = "badge badge-info", stopped_reason
        return f'<span class="{css}">{html.escape(label)}</span>'

    @staticmethod
    def _token_card(tokens_used: int) -> str:
        if not tokens_used:
            return ""
        return f'<div class="card"><h3>Tokens used</h3><p>{tokens_used:,}</p></div>'

    @staticmethod
    def _cost_card(estimated_cost_usd: float) -> str:
        if not estimated_cost_usd:
            return ""
        return f'<div class="card"><h3>Estimated cost</h3><p>${estimated_cost_usd:,.4f}</p></div>'

    def _insights_section(self, insights: ReportInsights) -> str:
        if not insights.has_content():
            return ""

        parts = ['<section class="section"><h2 class="section-title">AI Review Insights</h2>']

        if insights.summary:
            parts.append(
                f'<div class="insight insight-summary">'
                f'<h4>Summary</h4><p>{html.escape(insights.summary)}</p></div>'
            )

        if insights.key_changes:
            parts.append(self._key_changes_table(insights.key_changes))

        if insights.risks:
            parts.append(self._risks_table(insights.risks))

        if insights.review_focus:
            parts.append(self._review_focus_table(insights.review_focus))

        if insights.next_actions:
            parts.append(self._next_actions_list(insights.next_actions))

        parts.append("</section>")
        return "\n".join(parts)

    def _key_changes_table(self, changes: list[KeyChange]) -> str:
        rows = []
        for change in changes:
            suggestions = "<ul>" + "".join(
                f"<li>{html.escape(s)}</li>" for s in change.review_suggestions
            ) + "</ul>" if change.review_suggestions else "<span class=\"empty\">—</span>"
            rows.append(
                f'<tr>'
                f'<td><code>{html.escape(change.file)}</code></td>'
                f'<td><span class="badge badge-{self._level_color(change.complexity)}">{html.escape(change.change_type)}</span></td>'
                f'<td>{self._level_badge(change.complexity)}</td>'
                f'<td>{self._level_badge(change.risk_level)}</td>'
                f'<td>{html.escape(change.description)}</td>'
                f'<td>{suggestions}</td>'
                f'</tr>'
            )
        return (
            '<h3>Key Changes</h3>'
            '<table>'
            '<thead><tr><th>File</th><th>Type</th><th>Complexity</th><th>Risk</th><th>Description</th><th>Review Suggestions</th></tr></thead>'
            '<tbody>' + "\n".join(rows) + '</tbody>'
            '</table>'
        )

    def _risks_table(self, risks: list[Risk]) -> str:
        rows = []
        for risk in risks:
            files = ", ".join(f"<code>{html.escape(f)}</code>" for f in risk.files) or "—"
            rows.append(
                f'<tr>'
                f'<td>{self._level_badge(risk.level)}</td>'
                f'<td>{html.escape(risk.description)}</td>'
                f'<td>{files}</td>'
                f'</tr>'
            )
        return (
            '<h3>Risks</h3>'
            '<table>'
            '<thead><tr><th>Level</th><th>Description</th><th>Files</th></tr></thead>'
            '<tbody>' + "\n".join(rows) + '</tbody>'
            '</table>'
        )

    def _review_focus_table(self, focus_items: list[ReviewFocus]) -> str:
        rows = []
        for item in focus_items:
            rows.append(
                f'<tr>'
                f'<td><span class="badge badge-info">P{item.priority}</span></td>'
                f'<td>{html.escape(item.area)}</td>'
                f'<td>{html.escape(item.reason)}</td>'
                f'</tr>'
            )
        return (
            '<h3>Review Focus</h3>'
            '<table>'
            '<thead><tr><th>Priority</th><th>Area</th><th>Reason</th></tr></thead>'
            '<tbody>' + "\n".join(rows) + '</tbody>'
            '</table>'
        )

    def _next_actions_list(self, actions: list[NextAction]) -> str:
        urgency_order = {"now": 0, "before_merge": 1, "nice_to_have": 2}
        sorted_actions = sorted(actions, key=lambda a: urgency_order.get(a.urgency, 1))
        lines = ['<h3>Next Actions</h3><div class="action-list">']
        for action in sorted_actions:
            lines.append(
                f'<div class="action-card">'
                f'<span class="badge badge-{self._urgency_color(action.urgency)}">{html.escape(action.urgency)}</span>'
                f'<p>{html.escape(action.action)}</p>'
                f'</div>'
            )
        lines.append('</div>')
        return "\n".join(lines)

    @staticmethod
    def _level_color(level: str) -> str:
        level = level.lower()
        if level == "high":
            return "danger"
        if level == "medium":
            return "info"
        return "success"

    def _level_badge(self, level: str) -> str:
        color = self._level_color(level)
        return f'<span class="badge badge-{color}">{html.escape(level.lower())}</span>'

    @staticmethod
    def _urgency_color(urgency: str) -> str:
        urgency = urgency.lower()
        if urgency == "now":
            return "danger"
        if urgency == "before_merge":
            return "info"
        return "success"

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

    def _spec_status_rows(self) -> str:
        specs_dir = resolve_specs_dir(self.project_dir)
        specs = get_root_specs(specs_dir)
        if not specs:
            return '<tr><td colspan="3" class="empty">No spec files found.</td></tr>'
        rows = []
        for spec in specs:
            done = is_root_spec_complete(spec)
            status = (
                '<span class="badge badge-success">done</span>'
                if done
                else '<span class="badge badge-info">pending</span>'
            )
            priority = self._extract_priority(spec)
            rows.append(
                f'<tr>'
                f'<td>{html.escape(spec.name)}</td>'
                f'<td>{html.escape(priority)}</td>'
                f'<td>{status}</td>'
                f'</tr>'
            )
        return "\n".join(rows)

    @staticmethod
    def _extract_priority(spec: Path) -> str:
        for line in spec.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip().startswith("## Priority:"):
                return line.split(":", 1)[-1].strip()
        return "—"

    def _events_section(self, stopped_reason: str) -> str:
        events = self._load_events()
        if not events:
            return ""
        rows = "\n".join(self._event_row(e) for e in events)
        failures = [e for e in events if e.get("kind") in self.FAILURE_EVENT_KINDS]
        failure_summary = ""
        if failures:
            failure_items = "".join(
                f"<li><code>{html.escape(str(e.get('kind')))}</code> — "
                f"{html.escape(self._event_detail(e.get('data') or {}))}</li>"
                for e in failures
            )
            failure_summary = (
                '<div class="insight insight-summary">'
                "<h4>Failure Reasons</h4>"
                f"<ul>{failure_items}</ul>"
                "</div>"
            )
        return f"""
  <section class="section">
    <h2 class="section-title">Event Timeline</h2>
    <p>Final stop reason: {self._status_badge(stopped_reason)}</p>
    {failure_summary}
    <table>
      <thead>
        <tr><th>Time</th><th>Event</th><th>Details</th></tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>
  </section>
"""

    def _event_row(self, event: dict[str, Any]) -> str:
        kind = str(event.get("kind", ""))
        ts = str(event.get("ts", ""))
        data = event.get("data") or {}
        badge = "badge-danger" if kind in self.FAILURE_EVENT_KINDS else "badge-info"
        detail = html.escape(self._event_detail(data))
        return (
            "<tr>"
            f"<td>{html.escape(ts)}</td>"
            f'<td><span class="badge {badge}">{html.escape(kind)}</span></td>'
            f"<td>{detail}</td>"
            "</tr>"
        )

    @staticmethod
    def _event_detail(data: dict[str, Any]) -> str:
        parts = [f"{key}={value}" for key, value in data.items() if key != "line"]
        return ", ".join(parts)[:200]

    def _diff_summary(self, iterations: int) -> str:
        if iterations <= 0:
            return '<p class="empty">No commits to diff.</p>'
        import subprocess
        result = subprocess.run(
            ["git", "diff", "--stat", f"HEAD~{iterations}..HEAD"],
            cwd=self.project_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return '<p class="empty">Could not generate diff summary.</p>'
        return f'<pre class="diff-stat"><code>{html.escape(result.stdout.strip())}</code></pre>'
