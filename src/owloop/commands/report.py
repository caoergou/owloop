"""Implementation of the ``owloop report`` command."""

import os
import shutil
import subprocess
from pathlib import Path

from rich.console import Console

from owloop import _brand
from owloop.adapters import DEFAULT_IDLE_TIMEOUT, get_adapter
from owloop.cli_display import AgentStreamDisplay, _banner_text
from owloop.cli_options import _cli_options
from owloop.report import ReportGenerator
from owloop.report_ai import AIReportInsightsGenerator


def report_cmd(output: Path | None, ai: bool, open_report: bool, model: str) -> None:
    """Generate an HTML summary report for the latest owloop run.

    By default the report includes AI-generated insights (summary, risks,
    review focus) and is styled as a reviewable artifact. Use --no-ai for a
    fast, offline report.
    """
    ascii, no_color, _compact, verbose = _cli_options()
    console = Console(no_color=no_color)
    project_dir = Path.cwd()

    insights = None
    if ai:
        adapter = get_adapter(
            "claude",
            model=model,
            claude_cmd=os.environ.get("CLAUDE_CMD", "claude"),
            idle_timeout=DEFAULT_IDLE_TIMEOUT,
        )
        ai_generator = AIReportInsightsGenerator(project_dir, adapter)
        stream = AgentStreamDisplay(console, verbose=verbose)

        try:
            stream.start()
            insights = ai_generator.generate(on_line=stream.on_line)
        except FileNotFoundError:
            console.print("[red]Error:[/] No run summary found. Run [bold]owloop run[/] first.")
            raise SystemExit(1) from None
        except RuntimeError as exc:
            console.print(f"[{_brand.AMBER}]⚠ AI insights failed:[/] {exc}")
            console.print("[dim]Falling back to static report. Use --no-ai to skip AI.[/]")
        finally:
            stream.stop()

    if output is None and ai:
        output = project_dir / ".owloop" / "reports" / "owloop_report.html"

    generator = ReportGenerator(project_dir)
    try:
        report_path = generator.generate(output, insights=insights, use_tailwind=ai)
    except FileNotFoundError:
        console.print("[red]Error:[/] No run summary found. Run [bold]owloop run[/] first.")
        raise SystemExit(1) from None

    if open_report and ai:
        if shutil.which("lavish-axi"):
            console.print(f"[{_brand.AMBER}]Opening report with lavish-axi...[/]")
            subprocess.run(["lavish-axi", str(report_path)], check=False)
        else:
            console.print("[{_brand.AMBER}]⚠ lavish-axi not found:[/] report saved but not opened")

    console.print()
    console.print(_banner_text(ascii=ascii, no_color=no_color))
    console.print(f"[{_brand.GREEN}]✓ Report generated:[/] {report_path}")
    console.print()
