"""Implementation of the ``owloop init`` command."""

from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from owloop import _brand
from owloop.backpressure import discover_and_save
from owloop.cli_display import _banner_text
from owloop.cli_options import _cli_options

SPEC_TEMPLATE = """\
# Spec: {name}

## Priority: {priority}

## Requirements
- [ ] TODO: describe what needs to be done

## Acceptance Criteria
- [ ] TODO: shell command → expected output
      Verify: `echo "replace with real verification command"`

## Exclusions
- Do NOT modify files outside the scope described above
- Do NOT change any external API behavior
- Do NOT modify pyproject.toml, uv.lock, or other config files

## Style
- Follow existing project conventions

## Verification
The loop re-runs the Acceptance Criteria commands itself and commits only when
they pass — you never commit, push, or mark this spec COMPLETE. Do not edit this
section or the Acceptance Criteria mid-iteration.

Output when complete: `<promise>DONE</promise>`
"""


def init_cmd(example: bool) -> None:
    """Initialize owloop in the current project.

    Creates a single ``.owloop/`` metadata directory in the project root.
    All specs, logs, and runtime prompts live inside it so the original
    project stays clean.
    """
    ascii, no_color, _compact, verbose = _cli_options()
    console = Console(no_color=no_color)
    cwd = Path.cwd()

    if not (cwd / ".git").exists():
        console.print("[red]Error:[/] Not a git repository. Run [bold]git init[/] first.")
        raise SystemExit(1)

    owloop_path = cwd / ".owloop"
    specs_path = owloop_path / "specs"
    logs_path = owloop_path / "logs"

    created = []

    if not owloop_path.exists():
        owloop_path.mkdir(parents=True)
        created.append(".owloop/")

    if not specs_path.exists():
        specs_path.mkdir(parents=True)
        created.append(".owloop/specs/")

    if not logs_path.exists():
        logs_path.mkdir(parents=True)
        created.append(".owloop/logs/")

    gitignore = cwd / ".gitignore"
    gitignore_entries = [".owloop/"]
    if gitignore.exists():
        existing = gitignore.read_text(encoding="utf-8")
        to_add = [e for e in gitignore_entries if e not in existing]
        if to_add:
            with open(gitignore, "a", encoding="utf-8") as f:
                f.write("\n# owloop\n")
                for entry in to_add:
                    f.write(f"{entry}\n")
            created.append(".gitignore (updated)")
    else:
        gitignore.write_text("# owloop\n" + "\n".join(gitignore_entries) + "\n", encoding="utf-8")
        created.append(".gitignore")

    if example:
        example_spec = specs_path / "01-example.md"
        if not example_spec.exists():
            example_spec.write_text(
                SPEC_TEMPLATE.format(name="example-task", priority=1),
                encoding="utf-8",
            )
            created.append(".owloop/specs/01-example.md")

    backpressure_path = owloop_path / "backpressure.json"
    if not backpressure_path.exists():
        try:
            _commands, bp_path = discover_and_save(cwd)
            created.append(str(bp_path.relative_to(cwd)))
        except Exception:
            pass

    console.print()
    console.print(_banner_text(ascii=ascii, no_color=no_color))

    if created:
        console.print(
            Panel(
                "\n".join(f"  [green]✓[/] {f}" for f in created),
                title="[bold]Initialized[/]",
                border_style=_brand.AMBER,
                padding=(1, 2),
            )
        )
    else:
        console.print("[dim]Already initialized — nothing to create.[/]")

    console.print()
    console.print(f"[bold {_brand.AMBER}]Next steps:[/]")
    console.print("  1. Edit [bold].owloop/specs/01-example.md[/] with your task")
    console.print("  2. Run [bold]owloop run[/]")
    console.print()
