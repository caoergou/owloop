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


# ── mark_spec_complete / get_acceptance_criteria_section (engine gate support) ──


def test_mark_spec_complete_inserts_status_after_title(tmp_path: Path) -> None:
    spec = tmp_path / "01-t.md"
    spec.write_text("# Spec: t\n\n## Requirements\n- do it\n", encoding="utf-8")

    assert spec_queue.mark_spec_complete(spec) is True
    assert spec_queue.is_root_spec_complete(spec) is True
    text = spec.read_text(encoding="utf-8")
    assert "**Status**: COMPLETE" in text
    # Inserted right after the title, before Requirements.
    assert text.index("**Status**: COMPLETE") < text.index("## Requirements")


def test_mark_spec_complete_is_noop_when_already_complete(tmp_path: Path) -> None:
    spec = tmp_path / "01-t.md"
    spec.write_text("# Spec\n\n**Status**: COMPLETE\n\n## Requirements\n- x\n", encoding="utf-8")

    assert spec_queue.mark_spec_complete(spec) is False


def test_get_acceptance_criteria_section_includes_verification(tmp_path: Path) -> None:
    spec = tmp_path / "01-t.md"
    spec.write_text(
        "# Spec\n\n## Acceptance Criteria\n- `pytest -q`\n\n"
        "## Verification\nRun the tests.\n\n## Exclusions\n- none\n",
        encoding="utf-8",
    )
    section = spec_queue.get_acceptance_criteria_section(spec)
    assert "pytest -q" in section
    assert "Run the tests." in section
    # Stops at the next section (Exclusions is not part of the guarded region).
    assert "none" not in section


def test_get_acceptance_criteria_section_missing_returns_empty(tmp_path: Path) -> None:
    spec = tmp_path / "01-t.md"
    spec.write_text("# Spec\n\n## Requirements\n- x\n", encoding="utf-8")
    assert spec_queue.get_acceptance_criteria_section(spec) == ""


# ── acceptance-criteria command extraction ──


def test_get_acceptance_criteria_commands_extracts_plain_command(tmp_path: Path) -> None:
    spec = tmp_path / "01-t.md"
    spec.write_text(
        "# Spec\n\n## Acceptance Criteria\n- `pytest -q`\n- `ruff check .`\n",
        encoding="utf-8",
    )
    criteria = spec_queue.get_acceptance_criteria_commands(spec)
    assert [c.command for c in criteria] == ["pytest -q", "ruff check ."]
    assert all(not c.expect_no_output for c in criteria)


def test_get_acceptance_criteria_commands_detects_no_output(tmp_path: Path) -> None:
    spec = tmp_path / "01-t.md"
    spec.write_text(
        "# Spec\n\n## Acceptance Criteria\n"
        "- `grep foo bar.txt` → no output\n"
        "- `grep baz qux.txt` -> no output\n"
        "- `echo hi` → at least 1 match\n",
        encoding="utf-8",
    )
    criteria = spec_queue.get_acceptance_criteria_commands(spec)
    assert [c.command for c in criteria] == [
        "grep foo bar.txt",
        "grep baz qux.txt",
        "echo hi",
    ]
    assert criteria[0].expect_no_output is True
    assert criteria[1].expect_no_output is True
    assert criteria[2].expect_no_output is False


def test_get_acceptance_criteria_commands_ignores_free_form_bullets(tmp_path: Path) -> None:
    spec = tmp_path / "01-t.md"
    spec.write_text(
        "# Spec\n\n## Acceptance Criteria\n- just a free-form note\n- `true`\n",
        encoding="utf-8",
    )
    criteria = spec_queue.get_acceptance_criteria_commands(spec)
    assert [c.command for c in criteria] == ["true"]


# ── file-disjoint parallel scheduling (Phase 4) ──


def _scoped_spec(priority: int, files: list[str], depends_on: list[str] | None = None,
                 complete: bool = False) -> str:
    lines = ["# Spec: test", ""]
    if complete:
        lines += ["**Status**: COMPLETE", ""]
    lines += [f"## Priority: {priority}", ""]
    if depends_on is not None:
        lines += ["## Depends On"] + ([f"- {d}" for d in depends_on] or ["- none"]) + [""]
    lines += ["## Files"] + [f"- {f}" for f in files] + [""]
    lines += ["## Requirements", "Do a thing.", ""]
    return "\n".join(lines)


def test_get_spec_file_scope_parses_files_section(tmp_path: Path) -> None:
    spec = _write(tmp_path, "001-a.md", _scoped_spec(1, ["src/a/", "`tests/test_a.py`"]))
    assert spec_queue.get_spec_file_scope(spec) == ["src/a/", "tests/test_a.py"]


def test_get_spec_file_scope_missing_section_is_empty(tmp_path: Path) -> None:
    spec = _write(tmp_path, "001-a.md", _spec(priority=1))
    assert spec_queue.get_spec_file_scope(spec) == []


def test_specs_are_disjoint_true_for_separate_dirs(tmp_path: Path) -> None:
    a = _write(tmp_path, "001-a.md", _scoped_spec(1, ["src/a/"]))
    b = _write(tmp_path, "002-b.md", _scoped_spec(1, ["src/b/"]))
    assert spec_queue.specs_are_disjoint(a, b) is True


def test_specs_are_disjoint_false_on_overlap(tmp_path: Path) -> None:
    a = _write(tmp_path, "001-a.md", _scoped_spec(1, ["src/a/"]))
    b = _write(tmp_path, "002-b.md", _scoped_spec(1, ["src/a/util.py"]))
    assert spec_queue.specs_are_disjoint(a, b) is False


def test_specs_are_disjoint_false_on_glob_match(tmp_path: Path) -> None:
    a = _write(tmp_path, "001-a.md", _scoped_spec(1, ["src/*.py"]))
    b = _write(tmp_path, "002-b.md", _scoped_spec(1, ["src/main.py"]))
    assert spec_queue.specs_are_disjoint(a, b) is False


def test_specs_are_disjoint_false_when_scope_unknown(tmp_path: Path) -> None:
    a = _write(tmp_path, "001-a.md", _scoped_spec(1, ["src/a/"]))
    b = _write(tmp_path, "002-b.md", _spec(priority=1))  # no ## Files
    assert spec_queue.specs_are_disjoint(a, b) is False


def test_get_parallel_batch_groups_disjoint_specs(tmp_path: Path) -> None:
    specs = tmp_path / "specs"
    _write(specs, "001-a.md", _scoped_spec(1, ["src/a/"]))
    _write(specs, "002-b.md", _scoped_spec(1, ["src/b/"]))
    _write(specs, "003-c.md", _scoped_spec(1, ["src/a/deep.py"]))  # conflicts with a
    batch = spec_queue.get_parallel_batch(specs, max_workers=4)
    names = {p.name for p in batch}
    assert names == {"001-a.md", "002-b.md"}  # c excluded (overlaps a)


def test_get_parallel_batch_respects_max_workers(tmp_path: Path) -> None:
    specs = tmp_path / "specs"
    _write(specs, "001-a.md", _scoped_spec(1, ["src/a/"]))
    _write(specs, "002-b.md", _scoped_spec(1, ["src/b/"]))
    _write(specs, "003-c.md", _scoped_spec(1, ["src/c/"]))
    batch = spec_queue.get_parallel_batch(specs, max_workers=2)
    assert len(batch) == 2


def test_get_parallel_batch_lead_without_scope_runs_alone(tmp_path: Path) -> None:
    specs = tmp_path / "specs"
    _write(specs, "001-a.md", _spec(priority=1))  # highest priority, no ## Files
    _write(specs, "002-b.md", _scoped_spec(2, ["src/b/"]))
    batch = spec_queue.get_parallel_batch(specs, max_workers=4)
    assert [p.name for p in batch] == ["001-a.md"]


def test_get_parallel_batch_max_workers_one_is_sequential(tmp_path: Path) -> None:
    specs = tmp_path / "specs"
    _write(specs, "001-a.md", _scoped_spec(1, ["src/a/"]))
    _write(specs, "002-b.md", _scoped_spec(1, ["src/b/"]))
    assert len(spec_queue.get_parallel_batch(specs, max_workers=1)) == 1


def test_get_parallel_batch_empty_when_nothing_ready(tmp_path: Path) -> None:
    specs = tmp_path / "specs"
    _write(specs, "001-a.md", _scoped_spec(1, ["src/a/"], complete=True))
    assert spec_queue.get_parallel_batch(specs, max_workers=4) == []
