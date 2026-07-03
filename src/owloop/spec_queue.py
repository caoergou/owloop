"""Spec discovery and status helpers — Python port of scripts/lib/spec_queue.sh.

Spec status convention:
  A spec is COMPLETE if it contains a line matching (at line start):
    Status: COMPLETE
    **Status**: COMPLETE
    ## Status: COMPLETE

  Any other status (Draft, TODO, In Progress, or missing) means INCOMPLETE.

Spec priority:
  Lower number = higher priority. Files are sorted lexicographically,
  so 001-foo.md is picked before 100-bar.md.
"""

import re
from pathlib import Path

_COMPLETE_RE = re.compile(r"^(#{1,3} )?(\*\*)?Status(\*\*)?:\s+COMPLETE", re.MULTILINE)


def get_root_specs(specs_dir: Path) -> list[Path]:
    if not specs_dir.is_dir():
        return []
    return sorted(p for p in specs_dir.iterdir() if p.is_file() and p.suffix == ".md")


def is_root_spec_complete(spec_file: Path) -> bool:
    if not spec_file.is_file():
        return False
    return bool(_COMPLETE_RE.search(spec_file.read_text(encoding="utf-8", errors="replace")))


def get_incomplete_root_specs(specs_dir: Path) -> list[Path]:
    return [p for p in get_root_specs(specs_dir) if not is_root_spec_complete(p)]


def count_root_specs(specs_dir: Path) -> int:
    return len(get_root_specs(specs_dir))


def count_incomplete_root_specs(specs_dir: Path) -> int:
    return len(get_incomplete_root_specs(specs_dir))


def get_first_incomplete_root_spec(specs_dir: Path) -> Path | None:
    incomplete = get_incomplete_root_specs(specs_dir)
    return incomplete[0] if incomplete else None
