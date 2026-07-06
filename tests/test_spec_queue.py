"""Tests for spec_queue: priority, Depends On parsing, cycles, and topological selection."""

from __future__ import annotations

from pathlib import Path

from owloop import spec_queue


def _spec(priority: int, depends_on: list[str] | None = None, complete: bool = False) -> str:
    lines = ["# Spec: test", ""]
    if complete:
        lines += ["**Status**: COMPLETE", ""]
    lines += [f"## Priority: {priority}", ""]
    if depends_on is not None:
        lines += ["## Depends On"]
        lines += [f"- {dep}" for dep in depends_on] if depends_on else ["- none"]
        lines.append("")
    lines += ["## Requirements", "Do a thing.", ""]
    return "\n".join(lines)


def _write(specs_dir: Path, name: str, content: str) -> Path:
    specs_dir.mkdir(parents=True, exist_ok=True)
    path = specs_dir / name
    path.write_text(content, encoding="utf-8")
    return path


def test_get_spec_priority_reads_priority_section(tmp_path: Path) -> None:
    spec = _write(tmp_path, "001-a.md", _spec(priority=2))
    assert spec_queue.get_spec_priority(spec) == 2


def test_get_spec_priority_defaults_when_missing(tmp_path: Path) -> None:
    spec = _write(tmp_path, "001-a.md", "# Spec: test\n\n## Requirements\nDo a thing.\n")
    assert spec_queue.get_spec_priority(spec) == spec_queue.DEFAULT_PRIORITY


def test_get_dependency_tokens_missing_section_is_empty(tmp_path: Path) -> None:
    spec = _write(tmp_path, "001-a.md", _spec(priority=1))
    assert spec_queue.get_dependency_tokens(spec) == []


def test_get_dependency_tokens_none_entry_is_empty(tmp_path: Path) -> None:
    spec = _write(tmp_path, "001-a.md", _spec(priority=1, depends_on=[]))
    assert spec_queue.get_dependency_tokens(spec) == []


def test_get_dependency_tokens_parses_bullets(tmp_path: Path) -> None:
    spec = _write(tmp_path, "001-a.md", _spec(priority=1, depends_on=["002-b", "003-c.md"]))
    assert spec_queue.get_dependency_tokens(spec) == ["002-b", "003-c.md"]


def test_resolve_dependency_token_matches_stem_and_full_name(tmp_path: Path) -> None:
    specs_dir = tmp_path / "specs"
    spec_b = _write(specs_dir, "002-b.md", _spec(priority=1))

    assert spec_queue.resolve_dependency_token("002-b", [spec_b]) == spec_b
    assert spec_queue.resolve_dependency_token("002-b.md", [spec_b]) == spec_b


def test_resolve_dependency_token_strips_numeric_prefix(tmp_path: Path) -> None:
    specs_dir = tmp_path / "specs"
    spec_b = _write(specs_dir, "002-extract-helpers.md", _spec(priority=1))

    assert spec_queue.resolve_dependency_token("extract-helpers", [spec_b]) == spec_b


def test_resolve_dependency_token_unknown_returns_none(tmp_path: Path) -> None:
    specs_dir = tmp_path / "specs"
    spec_b = _write(specs_dir, "002-b.md", _spec(priority=1))

    assert spec_queue.resolve_dependency_token("does-not-exist", [spec_b]) is None


def test_get_spec_dependencies_ignores_unresolved_tokens(tmp_path: Path) -> None:
    specs_dir = tmp_path / "specs"
    spec_a = _write(specs_dir, "001-a.md", _spec(priority=1, depends_on=["typo-spec"]))

    assert spec_queue.get_spec_dependencies(spec_a, [spec_a]) == []


def test_build_dependency_graph_resolves_edges(tmp_path: Path) -> None:
    specs_dir = tmp_path / "specs"
    spec_b = _write(specs_dir, "002-b.md", _spec(priority=1))
    spec_a = _write(specs_dir, "001-a.md", _spec(priority=1, depends_on=["002-b"]))

    graph = spec_queue.build_dependency_graph(specs_dir)

    assert graph[spec_a] == [spec_b]
    assert graph[spec_b] == []


def test_find_cycle_detects_two_node_cycle(tmp_path: Path) -> None:
    specs_dir = tmp_path / "specs"
    spec_a = _write(specs_dir, "001-a.md", _spec(priority=1, depends_on=["002-b"]))
    spec_b = _write(specs_dir, "002-b.md", _spec(priority=1, depends_on=["001-a"]))

    graph = spec_queue.build_dependency_graph(specs_dir)
    cycle = spec_queue.find_cycle(graph)

    assert cycle is not None
    assert spec_a in cycle
    assert spec_b in cycle


def test_find_cycle_returns_none_for_acyclic_graph(tmp_path: Path) -> None:
    specs_dir = tmp_path / "specs"
    _write(specs_dir, "002-b.md", _spec(priority=1))
    _write(specs_dir, "001-a.md", _spec(priority=1, depends_on=["002-b"]))

    graph = spec_queue.build_dependency_graph(specs_dir)

    assert spec_queue.find_cycle(graph) is None


def test_get_next_ready_spec_skips_blocked_dependency(tmp_path: Path) -> None:
    specs_dir = tmp_path / "specs"
    # 001-a depends on 002-b (incomplete) so it isn't ready even though its
    # priority number is lower than 003-c's.
    _write(specs_dir, "001-a.md", _spec(priority=1, depends_on=["002-b"]))
    _write(specs_dir, "002-b.md", _spec(priority=5))
    spec_c = _write(specs_dir, "003-c.md", _spec(priority=2))

    assert spec_queue.get_next_ready_spec(specs_dir) == spec_c


def test_get_next_ready_spec_unblocks_once_dependency_completes(tmp_path: Path) -> None:
    specs_dir = tmp_path / "specs"
    spec_a = _write(specs_dir, "001-a.md", _spec(priority=1, depends_on=["002-b"]))
    _write(specs_dir, "002-b.md", _spec(priority=5, complete=True))

    assert spec_queue.get_next_ready_spec(specs_dir) == spec_a


def test_get_next_ready_spec_tie_breaks_by_priority_then_filename(tmp_path: Path) -> None:
    specs_dir = tmp_path / "specs"
    spec_low_priority = _write(specs_dir, "002-b.md", _spec(priority=1))
    _write(specs_dir, "001-a.md", _spec(priority=3))

    assert spec_queue.get_next_ready_spec(specs_dir) == spec_low_priority


def test_get_next_ready_spec_tie_breaks_by_filename_when_priority_equal(tmp_path: Path) -> None:
    specs_dir = tmp_path / "specs"
    spec_first = _write(specs_dir, "001-a.md", _spec(priority=1))
    _write(specs_dir, "002-b.md", _spec(priority=1))

    assert spec_queue.get_next_ready_spec(specs_dir) == spec_first


def test_get_next_ready_spec_returns_none_when_fully_blocked_by_cycle(tmp_path: Path) -> None:
    specs_dir = tmp_path / "specs"
    _write(specs_dir, "001-a.md", _spec(priority=1, depends_on=["002-b"]))
    _write(specs_dir, "002-b.md", _spec(priority=1, depends_on=["001-a"]))

    assert spec_queue.get_next_ready_spec(specs_dir) is None


def test_get_next_ready_spec_ignores_missing_dependency_tokens(tmp_path: Path) -> None:
    specs_dir = tmp_path / "specs"
    spec_a = _write(specs_dir, "001-a.md", _spec(priority=1, depends_on=["not-a-real-spec"]))

    assert spec_queue.get_next_ready_spec(specs_dir) == spec_a


def test_get_next_ready_spec_no_specs_returns_none(tmp_path: Path) -> None:
    assert spec_queue.get_next_ready_spec(tmp_path / "empty") is None
