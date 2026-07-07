"""Implementation of the ``owloop check`` command."""

from pathlib import Path

from rich.console import Console

from owloop import _brand
from owloop.cli_display import _banner_text
from owloop.cli_options import _cli_options
from owloop.paths import resolve_specs_dir
from owloop.spec_linter import LintReport, SpecLinter
from owloop.spec_review import SpecReview


def _print_check_report(console: Console, report: LintReport, *, ascii: bool = False) -> None:
    """Render a Rich report from a SpecLinter lint result."""
    check_icon = "+" if ascii else "✓"
    error_icon = "x" if ascii else "✗"
    warn_icon = "!" if ascii else "⚠"

    console.print()
    console.print("[bold]owloop check[/]")
    console.print(f"[dim]{'─' * 12}[/]")
    console.print(f"{check_icon} {report.spec_count} specs scanned")

    if report.error_count or report.warning_count:
        console.print(
            f"[{_brand.RED}]{error_icon} {report.error_count} error"
            f"{'s' if report.error_count != 1 else ''}[/], "
            f"[{_brand.AMBER}]{warn_icon} {report.warning_count} warning"
            f"{'s' if report.warning_count != 1 else ''}[/]"
        )
    else:
        console.print(f"[{_brand.GREEN}]{check_icon} 0 errors, 0 warnings[/]")

    for file_name, findings in report.results.items():
        if not findings:
            continue
        console.print()
        console.print(file_name)
        for finding in findings:
            if finding.severity == "error":
                icon = f"[{_brand.RED}]{error_icon}[/]"
            else:
                icon = f"[{_brand.AMBER}]{warn_icon}[/]"
            console.print(f"  {icon} {finding.message}")
    console.print()


def check_cmd(strict: bool, run_baseline: bool, review: bool) -> None:
    """Validate all specs before running the loop."""
    ascii, no_color, _compact, verbose = _cli_options()
    console = Console(no_color=no_color)
    specs_dir = resolve_specs_dir(Path.cwd())

    if not specs_dir.is_dir():
        console.print()
        console.print(_banner_text(ascii=ascii, no_color=no_color))
        console.print("[dim]No specs directory. Run [bold]owloop init[/] first.[/]")
        console.print()
        raise SystemExit(0)

    if review:
        project_dir = specs_dir.parent
        reviewer = SpecReview(specs_dir, project_dir=project_dir)
        has_errors = False
        has_warnings = False
        for spec_file in sorted(specs_dir.glob("*.md")):
            report = reviewer.review(spec_file, auto_fix=True)
            console.print(f"\n[bold]Review:[/] {spec_file.name}")
            if report.auto_fixed:
                console.print(f"  [green]✓ auto-fixed {len(report.auto_fixed)} issue(s)[/]")
            for finding in report.findings:
                icon = "✗" if finding.severity == "error" else "⚠"
                color = _brand.RED if finding.severity == "error" else _brand.AMBER
                console.print(f"  [{color}]{icon}[/] {finding.message}")
                if finding.severity == "error":
                    has_errors = True
                else:
                    has_warnings = True
        if has_errors or (strict and has_warnings):
            raise SystemExit(1)
        return

    linter = SpecLinter(specs_dir)
    lint_report = linter.lint_all(run_baseline=run_baseline)
    _print_check_report(console, lint_report, ascii=ascii)

    failed = lint_report.error_count > 0 or (strict and lint_report.warning_count > 0)
    if failed:
        raise SystemExit(1)
