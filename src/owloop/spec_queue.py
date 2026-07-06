"""Spec discovery and status helpers — Python port of scripts/lib/spec_queue.sh.

Spec status convention:
  A spec is COMPLETE if it contains a line matching (at line start):
    Status: COMPLETE
    **Status**: COMPLETE
    ## Status: COMPLETE

  Any other status (Draft, TODO, In Progress, or missing) means INCOMPLETE.

Spec priority:
  Lower number = higher priority, read from a `## Priority: N` section.
  Specs without a parseable priority fall back to DEFAULT_PRIORITY (lowest).

Spec dependencies:
  A `## Depends On` section lists other specs this one requires to be
  COMPLETE first, one per bullet (spec filename, filename without ".md", or
  filename without its numeric prefix). Missing, empty, or "none" sections
  mean no dependencies. Tokens that don't resolve to a known spec file are
  ignored rather than treated as blocking.

  `get_next_ready_spec` performs topological selection: among incomplete
  specs whose dependencies are all complete, it picks the lowest Priority
  number, then the lexicographically earliest filename.
"""

import re
from pathlib import Path

_COMPLETE_RE = re.compile(r"^(#{1,3} )?(\*\*)?Status(\*\*)?:\s+COMPLETE", re.MULTILINE)
_PRIORITY_RE = re.compile(r"^##\s+Priority:?\s*(\d+)", re.IGNORECASE | re.MULTILINE)
_DEPENDS_ON_SECTION_RE = re.compile(
    r"^##\s+Depends On\s*$\n(.*?)(?=^#{1,2}\s|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
_LIST_ITEM_RE = re.compile(r"^\s*-\s*(.+?)\s*$", re.MULTILINE)
_NUMERIC_PREFIX_RE = re.compile(r"^\d+-")
_ACCEPTANCE_CRITERIA_SECTION_RE = re.compile(
    r"^##\s+Acceptance Criteria\s*$\n(.*?)(?=^#{1,2}\s|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)

DEFAULT_PRIORITY = 999


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


def find_next_spec_number(specs_dir: Path) -> int:
    """Return the next available spec number (1, 2, 3...).

    Finds the highest existing numeric prefix in specs/*.md and adds one.
    Non-numeric filenames are ignored.
    """
    max_num = 0
    for path in get_root_specs(specs_dir):
        stem = path.stem
        prefix = stem.split("-", 1)[0] if "-" in stem else stem
        if prefix.isdigit():
            max_num = max(max_num, int(prefix))
    return max_num + 1


def get_spec_priority(spec_file: Path) -> int:
    """Read the `## Priority: N` value from a spec; DEFAULT_PRIORITY if absent/unparseable."""
    if not spec_file.is_file():
        return DEFAULT_PRIORITY
    content = spec_file.read_text(encoding="utf-8", errors="replace")
    match = _PRIORITY_RE.search(content)
    return int(match.group(1)) if match else DEFAULT_PRIORITY


def get_dependency_tokens(spec_file: Path) -> list[str]:
    """Return the raw bullet tokens listed under a spec's `## Depends On` section.

    Missing sections, empty sections, and "none" entries yield an empty list.
    """
    if not spec_file.is_file():
        return []
    content = spec_file.read_text(encoding="utf-8", errors="replace")
    match = _DEPENDS_ON_SECTION_RE.search(content)
    if match is None:
        return []

    tokens: list[str] = []
    for item in _LIST_ITEM_RE.findall(match.group(1)):
        cleaned = item.strip().strip("`").strip()
        if not cleaned or cleaned.lower() == "none":
            continue
        tokens.append(cleaned)
    return tokens


def resolve_dependency_token(token: str, specs: list[Path]) -> Path | None:
    """Match a Depends On bullet token to a spec file among ``specs``."""
    normalized = token[: -len(".md")] if token.lower().endswith(".md") else token
    normalized = normalized.strip()
    if not normalized:
        return None

    for spec in specs:
        if spec.name == normalized or spec.stem == normalized:
            return spec
    for spec in specs:
        if _NUMERIC_PREFIX_RE.sub("", spec.stem) == normalized:
            return spec

    candidates = [spec for spec in specs if normalized in spec.stem]
    return candidates[0] if len(candidates) == 1 else None


def get_spec_dependencies(spec_file: Path, specs: list[Path]) -> list[Path]:
    """Resolve a spec's Depends On tokens to spec file paths from ``specs``.

    Tokens that don't resolve to a known spec (typos, external references)
    are silently dropped rather than treated as blocking.
    """
    resolved: list[Path] = []
    for token in get_dependency_tokens(spec_file):
        target = resolve_dependency_token(token, specs)
        if target is not None and target != spec_file:
            resolved.append(target)
    return resolved


def get_acceptance_criteria_commands(spec_file: Path) -> list[str]:
    """Extract the first backtick-quoted shell command from each Acceptance Criteria bullet.

    Bullets without a backtick-quoted command (free-form descriptions) are skipped.
    """
    if not spec_file.is_file():
        return []
    content = spec_file.read_text(encoding="utf-8", errors="replace")
    match = _ACCEPTANCE_CRITERIA_SECTION_RE.search(content)
    if match is None:
        return []

    commands: list[str] = []
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if "`" not in stripped:
            continue
        parts = stripped.split("`")
        if len(parts) < 3:
            continue
        command = parts[1].strip()
        if command:
            commands.append(command)
    return commands


def build_dependency_graph(specs_dir: Path) -> dict[Path, list[Path]]:
    """Build a mapping of spec file -> resolved spec files it depends on."""
    specs = get_root_specs(specs_dir)
    return {spec: get_spec_dependencies(spec, specs) for spec in specs}


def find_cycle(graph: dict[Path, list[Path]]) -> list[Path] | None:
    """Return one dependency cycle as an ordered path, or None if acyclic."""
    white, gray, black = 0, 1, 2
    color: dict[Path, int] = dict.fromkeys(graph, white)
    stack: list[Path] = []

    def visit(node: Path) -> list[Path] | None:
        color[node] = gray
        stack.append(node)
        for dep in graph.get(node, []):
            dep_color = color.get(dep, white)
            if dep_color == gray:
                cycle_start = stack.index(dep)
                return [*stack[cycle_start:], dep]
            if dep_color == white:
                found = visit(dep)
                if found is not None:
                    return found
        stack.pop()
        color[node] = black
        return None

    for node in graph:
        if color[node] == white:
            cycle = visit(node)
            if cycle is not None:
                return cycle
    return None


def get_next_ready_spec(specs_dir: Path) -> Path | None:
    """Return the highest-priority incomplete spec whose dependencies are complete.

    Ties break by lower Priority number, then lexicographically earlier filename.
    Returns None only when every incomplete spec is blocked (e.g. a dependency
    cycle among the remaining incomplete specs).
    """
    all_specs = get_root_specs(specs_dir)
    incomplete = get_incomplete_root_specs(specs_dir)
    incomplete_set = set(incomplete)

    ready = [
        spec
        for spec in incomplete
        if all(dep not in incomplete_set for dep in get_spec_dependencies(spec, all_specs))
    ]
    if not ready:
        return None

    ready.sort(key=lambda spec: (get_spec_priority(spec), spec.name))
    return ready[0]
