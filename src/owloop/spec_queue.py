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

import fnmatch
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
_VERIFICATION_SECTION_RE = re.compile(
    r"^##\s+Verification\s*$\n(.*?)(?=^#{1,2}\s|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
_FILES_SECTION_RE = re.compile(
    r"^##\s+Files\s*$\n(.*?)(?=^#{1,2}\s|\Z)",
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


def get_acceptance_criteria_section(spec_file: Path) -> str:
    """Return the raw text of a spec's ``## Acceptance Criteria`` section.

    Used for tamper detection: the engine snapshots this section (plus the
    Verification section) before an iteration and fails the iteration if the
    agent rewrote its own success conditions. Missing section yields "".
    """
    if not spec_file.is_file():
        return ""
    content = spec_file.read_text(encoding="utf-8", errors="replace")
    parts: list[str] = []
    for pattern in (_ACCEPTANCE_CRITERIA_SECTION_RE, _VERIFICATION_SECTION_RE):
        match = pattern.search(content)
        if match is not None:
            parts.append(match.group(1))
    return "\n".join(parts)


def mark_spec_complete(spec_file: Path) -> bool:
    """Insert a ``**Status**: COMPLETE`` line near the top of a spec.

    No-op (returns False) if the spec is already complete or missing. The
    status line is placed right after the leading ``# `` title so the next
    iteration's queue scan skips it. This is engine-owned: the build agent no
    longer marks its own work complete.
    """
    if not spec_file.is_file() or is_root_spec_complete(spec_file):
        return False
    content = spec_file.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()
    insert_at = 0
    for idx, line in enumerate(lines):
        if line.startswith("# "):
            insert_at = idx + 1
            break
    status_block = ["", "**Status**: COMPLETE"]
    lines[insert_at:insert_at] = status_block
    spec_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


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


def get_ready_specs(specs_dir: Path) -> list[Path]:
    """Return all incomplete specs whose dependencies are complete, in run order.

    Same readiness rule as ``get_next_ready_spec`` but returns the whole ready
    frontier, sorted by (Priority, filename). Because two *ready* specs can only
    depend on already-complete specs, they are guaranteed dependency-independent
    of each other — so parallel scheduling only has to reason about file scope.
    """
    all_specs = get_root_specs(specs_dir)
    incomplete = get_incomplete_root_specs(specs_dir)
    incomplete_set = set(incomplete)
    ready = [
        spec
        for spec in incomplete
        if all(dep not in incomplete_set for dep in get_spec_dependencies(spec, all_specs))
    ]
    ready.sort(key=lambda spec: (get_spec_priority(spec), spec.name))
    return ready


def get_spec_file_scope(spec_file: Path) -> list[str]:
    """Return the path/glob tokens a spec declares under its ``## Files`` section.

    This is the contract that makes safe parallelism possible: a spec that
    declares which files it touches can be scheduled alongside other specs whose
    scopes don't overlap. A missing/empty section yields ``[]`` — an unknown
    scope, which the scheduler treats conservatively (never parallel-safe).
    """
    if not spec_file.is_file():
        return []
    content = spec_file.read_text(encoding="utf-8", errors="replace")
    match = _FILES_SECTION_RE.search(content)
    if match is None:
        return []
    scope: list[str] = []
    for item in _LIST_ITEM_RE.findall(match.group(1)):
        cleaned = item.strip().strip("`").strip()
        if cleaned and cleaned.lower() != "none":
            scope.append(cleaned)
    return scope


def _paths_conflict(a: str, b: str) -> bool:
    """True if two path/glob tokens could touch a common file."""
    if a == b:
        return True
    if fnmatch.fnmatch(a, b) or fnmatch.fnmatch(b, a):
        return True
    an, bn = a.rstrip("/"), b.rstrip("/")
    # Directory-prefix containment (only for non-glob tokens).
    if "*" not in a and "?" not in a and (bn == an or bn.startswith(an + "/")):
        return True
    if "*" not in b and "?" not in b and (an == bn or an.startswith(bn + "/")):  # noqa: SIM103
        return True
    return False


def scopes_overlap(scope_a: list[str], scope_b: list[str]) -> bool:
    """True if any token in one scope could touch a file in the other."""
    return any(_paths_conflict(a, b) for a in scope_a for b in scope_b)


def specs_are_disjoint(spec_a: Path, spec_b: Path) -> bool:
    """True if two specs declare non-empty, non-overlapping file scopes.

    An empty (undeclared) scope is never disjoint — the safe default is that an
    unscoped spec might touch anything, so it must not run in parallel.
    """
    scope_a = get_spec_file_scope(spec_a)
    scope_b = get_spec_file_scope(spec_b)
    if not scope_a or not scope_b:
        return False
    return not scopes_overlap(scope_a, scope_b)


def get_parallel_batch(specs_dir: Path, max_workers: int) -> list[Path]:
    """Select a batch of ready specs safe to run concurrently.

    Greedy: start from the highest-priority ready spec and add further ready
    specs whose declared ``## Files`` scope is disjoint from every spec already
    in the batch, up to ``max_workers``. If the lead spec has no declared scope
    the batch is just ``[lead]`` (run it alone) — correctness over parallelism.
    Returns ``[]`` only when nothing is ready.
    """
    ready = get_ready_specs(specs_dir)
    if not ready:
        return []
    if max_workers <= 1:
        return [ready[0]]

    lead = ready[0]
    batch = [lead]
    if not get_spec_file_scope(lead):
        return batch  # unknown scope → run alone

    for candidate in ready[1:]:
        if len(batch) >= max_workers:
            break
        if get_spec_file_scope(candidate) and all(
            specs_are_disjoint(candidate, chosen) for chosen in batch
        ):
            batch.append(candidate)
    return batch
