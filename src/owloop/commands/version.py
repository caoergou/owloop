"""Implementation of the ``owloop version`` command."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version

from rich.console import Console

from owloop import _brand
from owloop.cli_display import _banner_text
from owloop.cli_options import _cli_options


def version_cmd() -> None:
    """Show the owloop version."""
    ascii, no_color, _compact, verbose = _cli_options()
    console = Console(no_color=no_color)

    try:
        v = pkg_version("owloop")
    except PackageNotFoundError:
        v = "0.0.0-dev"

    console.print()
    console.print(_banner_text(ascii=ascii, no_color=no_color))
    console.print(f"[bold]owloop[/] [{_brand.AMBER}]v{v}[/]")
    console.print()
